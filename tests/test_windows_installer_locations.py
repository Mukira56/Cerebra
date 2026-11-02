"""Exercise native location policy against fixtures, without running Setup or reading the user profile."""
import os
from pathlib import Path
import subprocess

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows installer policy")
ROOT = Path(__file__).resolve().parents[1]

# This compilation-only shim shadows System.Environment in Common.cs/Installer.cs.
# Even the old source-checkout fallback is tested against a synthetic profile;
# neither the harness nor the tests inspect real registration or user data.
HARNESS = r'''
using System;
using System.IO;

internal static class Environment {
    internal enum SpecialFolder { LocalApplicationData, UserProfile, Programs, DesktopDirectory, ProgramFiles, ProgramFilesX86 }
    internal static string Fixture;
    internal static string GetFolderPath(SpecialFolder folder) { return Path.Combine(Fixture,folder.ToString()); }
    internal static string GetEnvironmentVariable(string name) { throw new Exception("Unexpected environment lookup: "+name); }
}

internal static class LocationTests {
    private static void Equal(string expected,string actual) {
        if(!string.Equals(expected,actual,StringComparison.OrdinalIgnoreCase)) throw new Exception("Location policy assertion failed: "+actual);
    }
    private static void Record(string target,string data,string settingsData=null) {
        Directory.CreateDirectory(target);
        Shared.WriteJson(Path.Combine(target,"aihq-install.json"),new { app_id=Shared.AppId, data_dir=data });
        Shared.WriteJson(Path.Combine(target,"desktop-settings.json"),new { app_id=Shared.AppId, data_dir=settingsData??data });
    }
    private static string UnexpectedRegistration() { throw new Exception("An isolated install read real-install registration."); }
    private static int Main(string[] args) {
        Environment.Fixture=args[1];
        string fresh=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Cerebra","data");
        string legacy=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"AI-Development-HQ","data");
        string target=Path.Combine(Environment.Fixture,"program"), retained=Path.Combine(Environment.Fixture,"retained-data");
        var options=new InstallOptions();
        switch(args[0]) {
            case "fresh":
                Equal(fresh,Shared.DefaultData);
                Equal(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","Cerebra"),options.Target);
                options.SelectRegisteredInstall(delegate {return null;}); options.ResolveData(); Equal(fresh,options.Data);
                break;
            case "source":
                options.Target=Path.GetDirectoryName(legacy); options.TargetExplicit=true;
                options.SelectRegisteredInstall(UnexpectedRegistration); options.ResolveData(); Equal(fresh,options.Data);
                break;
            case "upgrade":
                Record(target,retained); options.Target=target; options.TargetExplicit=true;
                options.SelectRegisteredInstall(UnexpectedRegistration); options.ResolveData(); Equal(retained,options.Data);
                break;
            case "legacy-upgrade":
                Record(target,legacy); options.Target=target; options.TargetExplicit=true;
                options.SelectRegisteredInstall(UnexpectedRegistration); options.ResolveData(); Equal(legacy,options.Data);
                break;
            case "explicit":
                // No valid install record is needed to respect an explicit data selection.
                Directory.CreateDirectory(target); File.WriteAllText(Path.Combine(target,"aihq-install.json"),"invalid fixture");
                options.Target=target; options.TargetExplicit=true; options.Data=retained; options.DataExplicit=true;
                options.SelectRegisteredInstall(UnexpectedRegistration); options.ResolveData(); Equal(retained,options.Data);
                break;
            case "registered":
                Record(target,retained); int calls=0;
                options.SelectRegisteredInstall(delegate {calls++;return target;}); options.ResolveData();
                Equal(target,options.Target); Equal(retained,options.Data);
                if(calls!=1) throw new Exception("Expected exactly one app-registration lookup.");
                break;
            case "unverified":
                options.SelectRegisteredInstall(delegate {return Path.GetDirectoryName(legacy);}); options.ResolveData();
                Equal(Shared.DefaultInstall,options.Target); Equal(fresh,options.Data);
                break;
            case "test-isolation":
                options.Target=target; options.TargetExplicit=true; options.Data=retained; options.DataExplicit=true; options.TestRegistration=true;
                options.SelectRegisteredInstall(UnexpectedRegistration); options.ResolveData(); Equal(retained,options.Data);
                break;
            case "test-needs-dir":
            case "test-needs-data":
                options.TestRegistration=true; options.TargetExplicit=args[0]=="test-needs-data"; options.DataExplicit=args[0]=="test-needs-dir";
                try {options.SelectRegisteredInstall(UnexpectedRegistration);throw new Exception("Unsafe test defaults accepted.");}
                catch(ArgumentException) {}
                break;
            case "mismatched":
            case "relative":
            case "drive-relative":
            case "missing-config":
                string stored=args[0]=="relative"?"relative-data":args[0]=="drive-relative"?"C:relative-data":retained;
                Record(target,stored,args[0]=="mismatched"?legacy:null);
                if(args[0]=="missing-config") File.Delete(Path.Combine(target,"desktop-settings.json"));
                options.Target=target; options.TargetExplicit=true;
                try {options.ResolveData();throw new Exception("Unverifiable upgrade data was accepted.");}
                catch(IOException error) {if(!error.Message.Contains("--data")) throw;}
                break;
            default: throw new Exception("Unknown fixture case.");
        }
        Console.WriteLine("Passed: "+args[0]); return 0;
    }
}
'''


@pytest.fixture(scope="module")
def location_harness(tmp_path_factory):
    compiler = Path(os.environ.get("WINDIR", "C:/Windows")) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    if not compiler.is_file():
        pytest.skip("Windows .NET Framework C# compiler is unavailable")
    folder = tmp_path_factory.mktemp("installer-location-policy")
    source, executable = folder / "LocationTests.cs", folder / "LocationTests.exe"
    source.write_text(HARNESS, encoding="utf-8")
    command = [str(compiler), "/nologo", "/target:exe", "/platform:x64", "/main:LocationTests", f"/out:{executable}"]
    command += [f"/r:{assembly}.dll" for assembly in (
        "System.Windows.Forms", "System.Drawing", "System.Web.Extensions",
        "System.IO.Compression", "System.IO.Compression.FileSystem",
    )]
    command += [str(ROOT / "packaging/windows" / name) for name in ("Common.cs", "Installer.cs")]
    command.append(str(source))
    result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    return executable


@pytest.mark.parametrize("case", [
    "fresh", "source", "upgrade", "legacy-upgrade", "explicit", "registered", "unverified",
    "test-isolation", "test-needs-dir", "test-needs-data", "mismatched", "relative", "drive-relative", "missing-config",
])
def test_installer_data_location_policy(location_harness, tmp_path, case):
    # Old source and old per-user data both exist. Fresh selection must ignore them.
    databases = [
        tmp_path / "UserProfile/AI-Development-HQ/data/hq.sqlite3",
        tmp_path / "LocalApplicationData/AI HQ/data/hq.sqlite3",
        tmp_path / "retained-data/hq.sqlite3",
    ]
    for database in databases:
        database.parent.mkdir(parents=True, exist_ok=True)
        database.write_bytes(b"private fixture history: leave unchanged")
    before = {database: database.read_bytes() for database in databases}
    result = subprocess.run([str(location_harness), case, str(tmp_path)], capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == f"Passed: {case}"
    assert {database: database.read_bytes() for database in databases} == before
    assert not (tmp_path / "LocalApplicationData/Cerebra/data").exists()
