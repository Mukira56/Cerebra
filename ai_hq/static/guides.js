"use strict";
// Setup guides for Business connections: what you need, quick steps, and a full step-by-step guide.
// Links are ids of fixed official pages; the server opens them in the user's browser (POST /api/open-link/<id>).
// Checked against the providers' public documentation in October 2026; menus can move, so steps name the page as well.
window.CerebraGuides = {
  etsy: {
    title: "Etsy",
    need: ["An Etsy seller account with an open shop (each further shop: its own Etsy account)", "An Etsy developer app: its keystring and shared secret", "An HTTPS web address you control, registered as the app's callback URL"],
    quick: ["Open your shop at etsy.com/sell (skip if you have one)", "Create an app on Etsy's developer site", "Register your HTTPS callback URL on the app", "Paste the keystring, shared secret and callback URL here, then Save", "Authorize Etsy, paste the address you land on, Finish, then Check connection", "More shops: sign out of Etsy, press Add another shop…, sign in as that shop and Finish (up to 5, different products in each)"],
    links: [["Open Etsy seller signup", "etsy_sell"], ["Your Etsy apps", "etsy_apps"]],
    sections: [
      {heading: "1. Open an Etsy shop (if you don't have one)", steps: [
        "Go to etsy.com/sell and choose Get started. Sign in or create an Etsy account.",
        "Follow Etsy's setup: shop preferences (language, country, currency), a shop name, your first listing, how you'll get paid, and a billing card.",
        "Etsy asks you to secure the account (two-factor sign-in) before the shop opens, and may charge a one-time shop setup fee, shown during setup.",
        "As a US seller you get paid by direct deposit to your US bank account, and Etsy asks for your SSN or EIN for tax reporting (a 1099-K when your sales pass the IRS threshold).",
        "Etsy's US fees: USD 0.20 to list each item for four months, a 6.5% transaction fee on each sale, and payment processing (3% + USD 0.25). Check Etsy's Fees & Payments policy for current amounts."],
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
      {heading: "5. Add more shops (up to 5), each selling different products", steps: [
        "Etsy allows one person to run several shops, but each shop needs its own Etsy account (its own email address), and the same item may not be listed in two of your shops. Give every shop its own products, ideally its own niche: for example one shop for planners, another for wall art.",
        "Open the second shop: sign out of Etsy, go to etsy.com/sell, create a new Etsy account with a different email address and set the shop up as in step 1.",
        "You don't need a second developer app. Your one app's personal access covers up to 5 shops, which is why Cerebra stops at 5.",
        "In your browser, sign out of Etsy (or sign in as the new shop's account), so Etsy signs in the right shop.",
        "In Cerebra press Add another shop… under “Your Etsy shops”. Etsy opens: sign in as the new shop's account and allow access.",
        "Copy the whole address you land on, paste it in “After Etsy authorization” and press Finish authorization. Cerebra finds the shop and lists it. A shop that's already connected is refused.",
        "Repeat for up to 5 shops. To remove one, press Disconnect next to it, and also remove the app's access in that shop's Etsy settings."]},
      {heading: "6. Using several shops", steps: [
        "When you create a draft (Business Studio › job › Run confirmed action › Create an Etsy draft listing), choose the shop in “Etsy shop”.",
        "Cerebra refuses a draft that would repeat an item already drafted in another of your shops: the same job, or the same title with different capitals or punctuation. Make a different product for the other shop instead.",
        "Orders from every shop are imported as sales on the Money page."]},
      {heading: "Rules to know", steps: [
        "Cerebra only creates DRAFT listings after a job is reviewed and you confirm. You publish them yourself in Etsy, after adding photos and files.",
        "Follow Etsy's Creativity Standards: disclose AI-assisted work and production partners where required, and only sell designs you have the right to sell.",
        "Access tokens refresh automatically. If you change the app's keys, authorize again."],
        links: [["Etsy Creativity Standards", "etsy_creativity"], ["Etsy API terms", "etsy_api_terms"]]}
    ]
  },
  freelancer: {
    title: "Freelancer.com",
    need: ["A Freelancer.com account with a complete profile", "An app on Freelancer.com's developer settings with permission to read projects and place bids", "An OAuth access token for your own account from that app"],
    quick: ["Complete your Freelancer.com profile and verify it", "Create an app at accounts.freelancer.com › Settings › Developer", "Get an access token for your own account", "Paste it on the Freelance page under Freelancer.com account, then Connect"],
    links: [["Freelancer.com developer settings", "freelancer_develop"], ["Freelancer.com API docs", "freelancer_api_docs"], ["User Agreement", "freelancer_terms"]],
    sections: [
      {heading: "1. Get your account ready", steps: [
        "Sign in to Freelancer.com. Complete your profile (photo, headline, skills, portfolio) and verify your email, phone and payment method if Freelancer.com asks: verified profiles win more bids.",
        "Check how many bids your membership gives you each month. Every bid Cerebra sends uses one."]},
      {heading: "2. Create a developer app and get a token", steps: [
        "Open accounts.freelancer.com › Settings › Developer and create an app. Describe it truthfully, e.g. “Personal tool to find projects and send my own bids”.",
        "Give it the permissions to read projects and to place bids. Freelancer.com may show some of these as advanced scopes that it approves before the app can use them.",
        "Get an OAuth access token for your own account from the app. If the page doesn't offer one, Freelancer.com's API docs explain the sign-in flow, and its identity team answers questions about app access.",
        "Keep the token private, like a password."],
        links: [["Developer settings", "freelancer_develop"], ["API docs", "freelancer_api_docs"]]},
      {heading: "3. Connect your account in Cerebra", steps: [
        "Open the Freelance page and find the panel Freelancer.com account.",
        "Paste the token in Access token and press Connect. Cerebra checks it with Freelancer.com and shows your username. A token Freelancer.com refuses isn't kept.",
        "Bids are only sent when you press Send on a proposal, or under your own Apply automatically rules."]},
      {heading: "4. Add up to 4 more accounts: each one a different person", steps: [
        "A Freelancer.com account belongs to one person, and login details must never be shared (its User Agreement). Don't open a second account of your own: sites like Upwork and Fiverr also close people who run several.",
        "A teammate who works with you creates their own Freelancer.com account and app, and gets their own token, on their own computer or with you watching.",
        "Under “Add another account”, type their full name in Whose account and they paste their token. Tick that the account belongs to them and that they pasted the token themselves, then press Add this account.",
        "Each project gets one bid, from one account. Two bids from linked accounts on the same project look like collusion. When you send a bid, choose the account in “From the account”.",
        "With Apply automatically on, each account gets its own daily number of bids. Wins are checked with the account that placed the bid, and that person does the work and talks to the client.",
        "To remove an account, press Disconnect next to it, and revoke its token on Freelancer.com."]},
      {heading: "Rules to know", steps: [
        "Freelancer.com's User Agreement limits automated access without its permission. Keep Apply automatically to a small daily number, or send bids by hand, and ask Freelancer.com if you plan to rely on automation.",
        "Write proposals that are true: never claim skills or work a teammate can't deliver."],
        links: [["User Agreement", "freelancer_terms"]]}
    ]
  },
  shopify: {
    title: "Shopify",
    need: ["A Shopify store (its address ends in .myshopify.com)", "Access to Shopify's Dev Dashboard from the organization that owns the store", "An app there with the scopes write_products and read_orders, installed on the store"],
    quick: ["Open the Dev Dashboard (dev.shopify.com) from the store owner's organization", "Create an app, give it write_products and read_orders, release a version", "Install the app on your store", "Copy the Client ID and secret from the app's Settings", "Paste the store address, Client ID and secret here, then Connect store"],
    links: [["Shopify Dev Dashboard", "shopify_dev"], ["Start a Shopify store", "shopify_start"], ["How the connection works", "shopify_cc_docs"]],
    sections: [
      {heading: "1. Have a store", steps: [
        "If you don't have one, start a store at shopify.com and choose a plan. Selling needs a paid plan once the trial ends.",
        "Find the store's address in the Shopify admin under Settings › Domains: the one ending in .myshopify.com, e.g. my-store.myshopify.com."],
        links: [["Start a Shopify store", "shopify_start"]]},
      {heading: "2. Create the app in the Dev Dashboard", steps: [
        "Since 1 January 2026 stores can't make new custom apps inside the admin, so the app is made in Shopify's Dev Dashboard instead.",
        "Open dev.shopify.com and sign in with the same Shopify account that owns the store, so the app and the store are in the same organization. Shopify refuses the connection otherwise.",
        "Create an app, for example “Cerebra drafts”.",
        "Open Versions, add the scopes write_products (to create draft products) and read_orders (to read sales), and release the version."],
        links: [["Shopify Dev Dashboard", "shopify_dev"]]},
      {heading: "3. Install it on the store and copy its keys", steps: [
        "On the app's Home, install it on your store and approve the permissions.",
        "Open the app's Settings and copy the Client ID and the Client secret. Keep the secret private, like a password."]},
      {heading: "4. Connect in Cerebra", steps: [
        "Open Business connections › Shopify stores.",
        "Paste the store address, Client ID and Client secret, then press Connect store. Cerebra asks Shopify for a token and shows the store's name and currency. The token lasts 24 hours and Cerebra asks for a new one by itself.",
        "If Shopify answers that the store isn't permitted, the app was made in a different organization: make it again from the store owner's account."],
        links: [["How the connection works", "shopify_cc_docs"]]},
      {heading: "5. Add more stores (up to 5)", steps: [
        "Each store needs its own app installed on it: repeat steps 2–4 for each store, then press Add this store. A store that's already connected is refused.",
        "Give each store its own products and audience. Shopify doesn't forbid the same product in several of your stores, but different stores for different niches reach more buyers and don't compete with each other.",
        "To remove a store, press Disconnect next to it, and uninstall the app in that store's admin."]},
      {heading: "Using your stores", steps: [
        "Draft products: from a reviewed Business job choose Run confirmed action › Create a Shopify draft product and pick the store. It's created as a Draft. You add the images or download files in Shopify, review it and set it Active yourself.",
        "Sales: orders from every store appear on the Money page. Each counts what the buyer paid after discounts and refunds, with tax left out and before Shopify's fees."]}
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
    title: "Gmail",
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
        "Data access (scopes): add …/auth/gmail.readonly and …/auth/gmail.send. Reading finds wins and replies; sending is used only for emails you send with one click from Prospects, or by automatic outreach if you switch it on. Cerebra never deletes or changes mail.",
        "While the app stays in Testing, Google signs you out after about 7 days. Connect again when that happens, or publish the app for personal use."],
        links: [["Google Auth Platform", "google_auth"]]},
      {heading: "4. Create the Desktop app client", steps: [
        "Open Clients › Create client. Choose Application type: Desktop app, and name it “Cerebra”.",
        "Copy the Client ID (it ends with .apps.googleusercontent.com) and the Client secret."],
        links: [["Google OAuth clients", "google_clients"]]},
      {heading: "5. Connect in Cerebra", steps: [
        "Paste the Client ID and Client secret, press Save Google settings, then Connect Gmail…. Google's page opens in your browser.",
        "Allow reading and sending. Google may warn that the app isn't verified, because it's your own app: choose Continue. If you connected before, connect again so Cerebra may send.",
        "Back in Cerebra, search your inbox and turn any order email into a Business Studio job. Emails go out only when you press Send on a business in Prospects, or within the rules you set in Automatic outreach.",
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
