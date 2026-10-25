"use strict";
// Setup guides for Business connections: what you need, quick steps, and a full step-by-step guide.
// Links are ids of fixed official pages; the server opens them in the user's browser (POST /api/open-link/<id>).
// Checked against the providers' public documentation in October 2026; menus can move, so steps name the page as well.
window.CerebraGuides = {
  etsy: {
    title: "Etsy",
    need: ["An Etsy seller account with an open shop", "An Etsy developer app: its keystring and shared secret", "An HTTPS web address you control, registered as the app's callback URL"],
    quick: ["Open your shop at etsy.com/sell (skip if you have one)", "Create an app on Etsy's developer site", "Register your HTTPS callback URL on the app", "Paste the keystring, shared secret and callback URL here, then Save", "Authorize Etsy, paste the address you land on, Finish, then Check connection"],
    links: [["Open Etsy seller signup", "etsy_sell"], ["Your Etsy apps", "etsy_apps"]],
    sections: [
      {heading: "1. Open an Etsy shop (if you don't have one)", steps: [
        "Go to etsy.com/sell and choose Get started. Sign in or create an Etsy account.",
        "Follow Etsy's setup: shop preferences (language, country, currency), a shop name, your first listing, how you'll get paid, and a billing card.",
        "Etsy asks you to secure the account (two-factor sign-in) before the shop opens. Some countries also pay a one-time setup fee.",
        "Etsy charges a listing fee per item and fees per sale. Check Etsy's current Fees & Payments policy for your country."],
        links: [["Open etsy.com/sell", "etsy_sell"]]},
      {heading: "2. Create your Etsy developer app", steps: [
        "Open Etsy's developer site and register a new app (Create a New App). Describe it truthfully, e.g. “Personal tool that prepares draft listings for my own shop”.",
        "New apps start with personal access: they can manage your own shop (up to 5 shops), which is all Cerebra needs. Do not request commercial access.",
        "On Your Apps, open the app and copy the KEYSTRING (Cerebra calls it the App keystring) and the SHARED SECRET.",
        "Keep both private, like passwords."],
        links: [["Register an Etsy app", "etsy_register"], ["Your Etsy apps", "etsy_apps"]]},
      {heading: "3. Register a callback URL", steps: [
        "Etsy only sends you back to a callback URL registered on your app. It must start with https:// and match exactly, including capital letters, “www” and any trailing slash.",
        "Use an HTTPS address you control, for example a page on your own website or a free GitHub Pages site (https://yourname.github.io/cerebra-callback). The page doesn't need to show anything.",
        "Add that exact address as the app's callback URL on Your Apps."],
        links: [["Etsy sign-in rules", "etsy_auth_docs"]]},
      {heading: "4. Connect in Cerebra", steps: [
        "Paste the App keystring, Shared secret and the Registered HTTPS callback URL, then press Save protected settings. Leave Shop ID empty if you don't know it.",
        "Press Authorize Etsy…: Etsy opens in your browser. Sign in and allow access to listings and shop.",
        "Etsy then sends your browser to your callback address. Copy the whole address from the browser's address bar (it contains code=… and state=…), even if the page itself is blank.",
        "Paste it in “After Etsy authorization”, press Finish authorization, then Check connection. Cerebra finds your shop ID by itself and shows the shop name."]},
      {heading: "Rules to know", steps: [
        "Cerebra only creates DRAFT listings after a job is reviewed and you confirm. You publish them yourself in Etsy, after adding photos and files.",
        "Follow Etsy's Creativity Standards: disclose AI-assisted work and production partners where required, and only sell designs you have the right to sell.",
        "Access tokens refresh automatically. If you change the app's keys, authorize again."],
        links: [["Etsy Creativity Standards", "etsy_creativity"], ["Etsy API terms", "etsy_api_terms"]]}
    ]
  },
  printify: {
    title: "Printify",
    need: ["A free Printify account", "A Printify store (connected to Etsy/Shopify, or a manual/API store)", "A personal access token with shop, catalog, products and uploads permissions"],
    quick: ["Sign up at printify.com (free)", "Add a store under My stores", "Generate a personal access token under My Profile › Connections", "Paste the token here, Save, then Check connection"],
    links: [["Printify signup", "printify_signup"], ["Printify API tokens", "printify_tokens"]],
    sections: [
      {heading: "1. Create a Printify account and store", steps: [
        "Sign up free at printify.com. There's no monthly fee on the free plan; you pay for products when orders are produced.",
        "Open My stores › Add new store. Connect your Etsy or Shopify shop, or choose the manual / API store option if you only want to design products first.",
        "Cerebra blocks orders, order imports and production entirely. It only makes draft products, so nothing is printed or charged by Cerebra."],
        links: [["Printify signup", "printify_signup"]]},
      {heading: "2. Get your API token", steps: [
        "In Printify, click your profile › My Profile (Manage account) › Connections, or open the API tokens page directly.",
        "Generate a personal access token. Give it a name like “Cerebra” and allow at least: shops read, catalog read, products read and write, uploads read and write.",
        "Copy the token immediately: Printify shows it only once. Tokens are valid for one year; then create a new one."],
        links: [["Printify API tokens", "printify_tokens"], ["Printify help: generate a token", "printify_token_help"]]},
      {heading: "3. Connect in Cerebra", steps: [
        "Paste the token as API token and press Save protected settings, then Check connection.",
        "If you have one store, Cerebra selects it automatically. If you have several, the check lists them: type the ID of the one to use in Shop ID and save.",
        "From a reviewed job you can then upload images to your Printify library and create draft products. Pick real blueprint, print provider and variant IDs from Printify's catalog."]}
    ]
  },
  images: {
    title: "Image generation (OpenAI)",
    need: ["An OpenAI API account (separate from a ChatGPT subscription)", "API credit or a payment method on that account", "An API secret key; image models may require organization verification"],
    quick: ["Sign in at platform.openai.com", "Add credit under Billing", "Create a secret key under API keys", "Paste it here, Save, then Check connection"],
    links: [["OpenAI API keys", "openai_keys"], ["OpenAI billing", "openai_billing"]],
    sections: [
      {heading: "1. Set up an OpenAI API account", steps: [
        "Sign in at platform.openai.com with your OpenAI account. API usage is billed separately from ChatGPT Plus/Pro and from Codex sign-in.",
        "Open Settings › Billing and add a payment method or prepaid credit. Set a monthly budget limit if you want a hard cap.",
        "Image models can require organization verification. If Check connection says the model isn't available, complete verification under Settings › Organization."],
        links: [["OpenAI billing", "openai_billing"], ["Organization settings", "openai_verify"]]},
      {heading: "2. Create an API key", steps: [
        "Open API keys › Create new secret key. Name it “Cerebra”; restricting it to image generation is fine.",
        "Copy it right away. OpenAI shows it only once."],
        links: [["OpenAI API keys", "openai_keys"]]},
      {heading: "3. Connect in Cerebra", steps: [
        "Paste the key as OpenAI API key. Leave Image model empty for the default, or enter an image model your account offers (see OpenAI's image generation guide).",
        "Save, then Check connection. Checking does not create an image and costs nothing.",
        "Each image is a separate, paid action that you confirm on a reviewed job. Generated images are marked as not yet independently reviewed."],
        links: [["OpenAI image generation guide", "openai_images_docs"]]}
    ]
  },
  gmail: {
    title: "Gmail (read-only)",
    need: ["Your Google account", "A free Google Cloud project with the Gmail API turned on", "An OAuth client of type Desktop app (client ID and client secret)"],
    quick: ["Create a Google Cloud project", "Enable the Gmail API", "Set up the sign-in screen and add yourself as a test user", "Create a Desktop app OAuth client", "Paste the ID and secret here, then Connect Gmail"],
    links: [["Google Cloud console", "google_console"], ["Enable the Gmail API", "google_gmail_api"]],
    sections: [
      {heading: "1. Create a Google Cloud project", steps: [
        "Open the Google Cloud console and sign in with the Google account whose mail you want to read.",
        "Use the project picker at the top › New project. Name it “Cerebra”. It's free; no billing account is needed for this."],
        links: [["Google Cloud console", "google_console"]]},
      {heading: "2. Turn on the Gmail API", steps: ["With the project selected, open APIs & Services › Library, search for Gmail API, and press Enable."],
        links: [["Gmail API page", "google_gmail_api"]]},
      {heading: "3. Set up the sign-in screen", steps: [
        "Open Google Auth Platform (formerly “OAuth consent screen”) and press Get started.",
        "Enter an app name (Cerebra) and your email. For Audience choose External. Under Test users add your own Gmail address.",
        "Data access (scopes): add …/auth/gmail.readonly. Cerebra asks only for read-only access.",
        "While the app stays in Testing, Google signs you out after about 7 days. Connect again when that happens, or publish the app for personal use."],
        links: [["Google Auth Platform", "google_auth"]]},
      {heading: "4. Create the Desktop app client", steps: [
        "Open Clients › Create client. Choose Application type: Desktop app, and name it “Cerebra”.",
        "Copy the Client ID (it ends with .apps.googleusercontent.com) and the Client secret."],
        links: [["Google OAuth clients", "google_clients"]]},
      {heading: "5. Connect in Cerebra", steps: [
        "Paste the Client ID and Client secret, press Save Google settings, then Connect Gmail…. Google's page opens in your browser.",
        "Allow read-only access. Google may warn that the app isn't verified, because it's your own app: choose Continue.",
        "Back in Cerebra, search your inbox and turn any order email into a Business Studio job. Nothing is read or sent automatically.",
        "To remove access later, press Disconnect Gmail and remove Cerebra under your Google Account's third-party connections."],
        links: [["Google third-party connections", "google_permissions"]]}
    ]
  },
  notify: {
    title: "Progress on your phone",
    need: ["Either the free ntfy app, or a Telegram account", "For Telegram: a bot you create with @BotFather (free)"],
    quick: ["ntfy: install the app, subscribe to the topic shown here, tick ntfy, Save, Send me a test", "Telegram: create a bot with @BotFather, paste its token, press Start in your bot, Find my chat, Save, Send me a test"],
    links: [["Get the ntfy app", "ntfy_app"], ["Open @BotFather", "telegram_botfather"]],
    sections: [
      {heading: "Option A: ntfy (simplest, no account)", steps: [
        "Install ntfy from Google Play, the App Store or ntfy.sh.",
        "In the app press + (Subscribe to topic) and type the exact topic shown in Cerebra (cerebra-…). Keep it private: anyone who knows it can read the messages.",
        "In Cerebra tick “Send progress notifications through ntfy”, press Save notifications, then Send me a test."],
        links: [["ntfy website", "ntfy_app"], ["ntfy phone app help", "ntfy_docs"]]},
      {heading: "Option B: your own Telegram bot", steps: [
        "In Telegram open @BotFather, send /newbot, then choose a name and a username ending in “bot”.",
        "BotFather replies with a token like 123456789:AA…. Paste it as Bot token here and Save notifications.",
        "Open your new bot in Telegram and press Start (or send it any message).",
        "Back in Cerebra press Find my chat. Your chat ID fills in. Tick Telegram, Save, then Send me a test."],
        links: [["Open @BotFather", "telegram_botfather"]]},
      {heading: "What gets sent", steps: ["Only the task's short title and its state (started, needs you, finished, failed). Never code, files, logs or client data. Keep secrets out of task titles."]}
    ]
  },
  fiverr: {
    title: "Fiverr (manual)",
    need: ["A Fiverr seller profile with your gigs", "Nothing to connect: Fiverr has no seller API, so orders are handled by hand"],
    quick: ["Become a seller and publish your gigs on Fiverr", "When an order arrives, paste its requirements into Business Studio", "Review the exported files yourself and deliver them in Fiverr"],
    links: [["Become a Fiverr seller", "fiverr_sell"], ["Fiverr AI guidelines", "fiverr_ai"]],
    sections: [
      {heading: "1. Set up as a seller", steps: [
        "On Fiverr choose Become a seller. Complete your profile (photo, description, skills) and verify your identity if Fiverr asks.",
        "Create gigs that describe exactly what you deliver, for example “one-page business website” or “original vector logo”."],
        links: [["Become a Fiverr seller", "fiverr_sell"]]},
      {heading: "2. Handle an order with Cerebra", steps: [
        "Open the order in Fiverr and copy the buyer's requirements and any messages.",
        "In Business Studio press + New business job, choose what to make and paste the brief. If the buyer asked for no AI, tick that box: Cerebra will refuse the job.",
        "Approve the plan; Cerebra plans, creates, checks and reviews it. Export the package, read everything yourself, then deliver the files through Fiverr."]},
      {heading: "3. Stay within Fiverr's rules", steps: [
        "Follow Fiverr's AI guidelines: be open about using AI where they require it, and respect buyers who don't want it.",
        "Cerebra never messages buyers for you. All communication on Fiverr stays with you."],
        links: [["Fiverr AI guidelines", "fiverr_ai"]]}
    ]
  }
};
