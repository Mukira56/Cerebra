"""When GitHub's API limit is used up by others on the same internet address, updates still work from its web pages. GitHub is simulated."""
import httpx
import pytest

from ai_hq import updater
from ai_hq.updater import PublicGitHub

REPOSITORY = "owner/app"
SITE = f"https://github.com/{REPOSITORY}/releases"
NAME = "Cerebra-Setup-9.9.9-Windows-x64.exe"


class GitHub:
    def __init__(self, api=403, latest="/v9.9.9", asset=200):
        self.api, self.latest, self.asset, self.asked = api, latest, asset, []

    def __call__(self, request):
        url = str(request.url)
        self.asked.append(url)
        if request.url.host == "api.github.com":
            if self.api == "unreachable":
                raise httpx.ConnectTimeout("timed out", request=request)
            if self.api == 200:
                return httpx.Response(200, json={"tag_name": "v9.9.9", "name": "Notes title", "body": "Notes", "assets": [
                    {"name": NAME, "size": 5, "browser_download_url": f"{SITE}/download/v9.9.9/{NAME}"}]})
            return httpx.Response(self.api, json={"message": "API rate limit exceeded"})
        if url == f"{SITE}/latest":
            return httpx.Response(302, headers={"location": f"https://github.com/{REPOSITORY}/releases/tag{self.latest}"}) if self.latest else httpx.Response(200, text="<html>")
        if "/download/" in url:
            return httpx.Response(self.asset, headers={"content-length": "29002752"})
        raise AssertionError(url)


@pytest.fixture
def github(monkeypatch):
    def install(**fields):
        answers = GitHub(**fields)
        real = httpx.Client
        monkeypatch.setattr(httpx, "Client", lambda **options: real(transport=httpx.MockTransport(answers), **options))
        monkeypatch.setattr(updater, "REPOSITORY", REPOSITORY)
        monkeypatch.setattr(updater, "API", f"https://api.github.com/repos/{REPOSITORY}")
        return answers
    return install


@pytest.mark.parametrize("limit", [403, 429])
def test_when_the_api_is_limited_the_release_comes_from_the_website(github, limit):
    github(api=limit)
    release = PublicGitHub().release()
    assert release["tagName"] == "v9.9.9" and release["body"] == ""
    assert release["assets"] == [{"name": NAME, "size": 29002752, "url": f"{SITE}/download/v9.9.9/{NAME}"},
                                 {"name": f"{NAME}.sha256", "size": 0, "url": f"{SITE}/download/v9.9.9/{NAME}.sha256"}]


def test_a_named_version_skips_the_latest_page(github):
    answers = github()
    assert PublicGitHub().release("v9.9.9")["tagName"] == "v9.9.9" and f"{SITE}/latest" not in answers.asked


def test_the_website_is_only_used_when_the_api_says_no(github):
    answers = github(api=200)
    assert PublicGitHub().release()["body"] == "Notes" and not any("github.com/owner" in url and "api." not in url for url in answers.asked)


def test_a_version_that_does_not_exist_is_not_found(github):
    github(asset=404)
    assert PublicGitHub().release("v9.9.8") is None


@pytest.mark.parametrize("latest", ["", "/nightly", "/v9.9.9-evil", "/v9.9.9/../../x"])
def test_anything_that_is_not_a_plain_version_is_refused(github, latest):
    github(latest=latest)
    with pytest.raises(ValueError, match="limiting update checks"):
        PublicGitHub().release()


def test_if_the_website_also_refuses_the_owner_is_told_to_wait(github):
    github(asset=429)
    with pytest.raises(ValueError, match="Try again in an hour"):
        PublicGitHub().release()


def test_the_download_addresses_pass_the_updaters_own_check(github):
    github()
    assert all(item["url"].startswith(f"https://github.com/{updater.REPOSITORY}/releases/download/") for item in PublicGitHub().release()["assets"])
    assert updater.INSTALLER.match(NAME)


def test_when_only_the_api_cant_be_reached_the_release_comes_from_the_website(github):
    github(api="unreachable")
    assert PublicGitHub().release()["tagName"] == "v9.9.9"


def test_when_github_cant_be_reached_at_all_the_owner_is_told_to_check_the_connection(monkeypatch):
    real = httpx.Client
    monkeypatch.setattr(updater, "REPOSITORY", REPOSITORY)
    monkeypatch.setattr(updater, "API", f"https://api.github.com/repos/{REPOSITORY}")

    def down(request):
        raise httpx.ConnectError("no route", request=request)
    monkeypatch.setattr(httpx, "Client", lambda **options: real(transport=httpx.MockTransport(down), **options))
    with pytest.raises(ValueError, match="could not be reached"):
        PublicGitHub().release()
