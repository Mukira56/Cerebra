using System;
using System.Collections.Generic;
using System.IO;
using System.Drawing;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

internal sealed class DesktopWindow : Form {
    private readonly WebView2 view = new WebView2();
    private readonly Label loading = new Label();
    private readonly int port;
    internal bool AllowClose;
    internal event Action ExitRequested;
    internal DesktopWindow(int value,bool smoke=false) {
        port=value; Text="Cerebra"; Width=1380; Height=900;
        MinimumSize=new Size(860,600); StartPosition=FormStartPosition.CenterScreen;
        BackColor=Color.FromArgb(16,22,32); Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        if(smoke) { ShowInTaskbar=false;StartPosition=FormStartPosition.Manual;Location=new Point(-20000,-20000); }
        loading.Text="Starting your workspace...";loading.ForeColor=Color.White;loading.Font=new Font("Segoe UI",14);
        loading.Dock=DockStyle.Fill;loading.TextAlign=ContentAlignment.MiddleCenter;
        view.Dock=DockStyle.Fill;Controls.Add(view);Controls.Add(loading);
        FormClosing+=delegate(object sender,FormClosingEventArgs args) {
            if(!AllowClose) { args.Cancel=true; if(ExitRequested!=null) ExitRequested(); }
        };
    }
    private bool Local(string value) {
        Uri uri;return Uri.TryCreate(value,UriKind.Absolute,out uri) && uri.Scheme=="http" && uri.Host=="127.0.0.1" && uri.Port==port && string.IsNullOrEmpty(uri.UserInfo);
    }
    internal async Task OpenWorkspace(string url) {
        if(!Local(url)) throw new InvalidOperationException("The workspace address is not the configured local service.");
        Show(); if(WindowState==FormWindowState.Minimized) WindowState=FormWindowState.Normal;
        // Started by the update helper (a background process), Windows won't let Activate() take the foreground and only
        // flashes the taskbar, so Cerebra seemed not to reopen. Raising it to the top of the window stack always works.
        TopMost=true; TopMost=false; BringToFront(); Activate();
        if(view.CoreWebView2==null) {
            string profile=Path.Combine((string)Shared.Config(Shared.Root)["data_dir"],"desktop-profile");
            var environment=await CoreWebView2Environment.CreateAsync(null,profile);
            await view.EnsureCoreWebView2Async(environment);
            var settings=view.CoreWebView2.Settings;
            settings.AreDevToolsEnabled=false;settings.AreDefaultContextMenusEnabled=true;
            // The page shows its own menu for app items. Where the native menu appears (text boxes, selected
            // text) keep only editing commands: no Inspect, Save as, Print, Back/Reload or link actions.
            view.CoreWebView2.ContextMenuRequested+=delegate(object sender,CoreWebView2ContextMenuRequestedEventArgs args) {
                var keep=new HashSet<string>(StringComparer.OrdinalIgnoreCase){"undo","redo","cut","copy","paste","pasteAndMatchStyle","selectAll","emoji","spellCheck"};
                var items=args.MenuItems;
                for(int index=items.Count-1;index>=0;index--) {
                    var item=items[index];
                    if(item.Kind==CoreWebView2ContextMenuItemKind.Separator) continue;
                    if(!keep.Contains(item.Name) && !item.Name.StartsWith("spellCheck",StringComparison.OrdinalIgnoreCase)) items.RemoveAt(index);
                }
                for(int index=items.Count-1;index>=0;index--) {
                    bool separator=items[index].Kind==CoreWebView2ContextMenuItemKind.Separator;
                    if(separator && (index==0 || index==items.Count-1 || items[index-1].Kind==CoreWebView2ContextMenuItemKind.Separator)) items.RemoveAt(index);
                }
                if(items.Count==0) args.Handled=true;
            };
            settings.AreBrowserAcceleratorKeysEnabled=false;settings.IsStatusBarEnabled=false;
            settings.IsPasswordAutosaveEnabled=false;settings.IsGeneralAutofillEnabled=false;
            settings.AreHostObjectsAllowed=false;settings.IsWebMessageEnabled=false;
            view.CoreWebView2.NavigationStarting+=delegate(object sender,CoreWebView2NavigationStartingEventArgs args) { if(!Local(args.Uri)) args.Cancel=true; };
            view.CoreWebView2.NewWindowRequested+=delegate(object sender,CoreWebView2NewWindowRequestedEventArgs args) { args.Handled=true; };
            view.CoreWebView2.DownloadStarting+=delegate(object sender,CoreWebView2DownloadStartingEventArgs args) { args.Cancel=true; };
            view.CoreWebView2.PermissionRequested+=delegate(object sender,CoreWebView2PermissionRequestedEventArgs args) { args.State=CoreWebView2PermissionState.Deny; };
            view.CoreWebView2.NavigationCompleted+=delegate { loading.Visible=false; };
            // The taskbar shows whether Cerebra is waiting for the owner, working, or has a problem (set by the page).
            view.CoreWebView2.DocumentTitleChanged+=delegate {
                string title=view.CoreWebView2.DocumentTitle??"";
                bool ours=title.StartsWith("Cerebra")||System.Text.RegularExpressions.Regex.IsMatch(title,@"^\(\d{1,3}\) Cerebra");
                Text=ours&&title.Length<=120?title:"Cerebra";
            };
            view.CoreWebView2.ProcessFailed+=delegate { loading.Text="The workspace renderer stopped. Use the tray menu to restart Cerebra.";loading.Visible=true;loading.BringToFront(); };
        }
        view.CoreWebView2.Navigate(url);
    }
    internal async Task SmokeCheck() {
        for(int attempt=0;attempt<100;attempt++) {
            string connected=await view.CoreWebView2.ExecuteScriptAsync("document.querySelector('#connection-status')?.textContent || ''");
            if(connected.Contains("Local connection")) {
                string result=await view.CoreWebView2.ExecuteScriptAsync("JSON.stringify({title:document.title,logo:!!document.querySelector('.brand-mark')?.naturalWidth,authenticated:document.querySelector('#connection-status').textContent.includes('Local connection'),native:true})");
                var decoded=Shared.Json.Deserialize<string>(result);
                var proof=Shared.Json.Deserialize<System.Collections.Generic.Dictionary<string,object>>(decoded);
                if(!Convert.ToBoolean(proof["logo"]) || !Convert.ToBoolean(proof["authenticated"])) throw new Exception("Native window did not load the authenticated workspace.");
                await view.CoreWebView2.ExecuteScriptAsync("location.hash='system'");
                bool system=false;
                for(int checkIndex=0;checkIndex<100;checkIndex++) {
                    string connectedSystem=await view.CoreWebView2.ExecuteScriptAsync("document.querySelectorAll('.diagram .node').length===12 && document.querySelectorAll('.diagram .node.ok').length>=2");
                    if(connectedSystem=="true") {system=true;break;}
                    await Task.Delay(200);
                }
                if(!system)throw new Exception("The native system view did not connect to telemetry.");
                proof["system_view_connected"]=true;
                var blocked=new TaskCompletionSource<bool>();
                EventHandler<CoreWebView2NavigationStartingEventArgs> check=delegate(object sender,CoreWebView2NavigationStartingEventArgs args) { if(!Local(args.Uri)) blocked.TrySetResult(args.Cancel); };
                view.CoreWebView2.NavigationStarting+=check;
                view.CoreWebView2.Navigate("https://example.invalid/desktop-boundary-test");
                if(await Task.WhenAny(blocked.Task,Task.Delay(5000))!=blocked.Task || !blocked.Task.Result) throw new Exception("External navigation was not blocked.");
                view.CoreWebView2.NavigationStarting-=check;
                proof["external_navigation_blocked"]=true;
                if(view.CoreWebView2.Settings.AreHostObjectsAllowed || view.CoreWebView2.Settings.IsWebMessageEnabled) throw new Exception("Native host bridge must stay disabled.");
                proof["host_bridge_disabled"]=true;
                string data=(string)Shared.Config(Shared.Root)["data_dir"];
                using(var screenshot=File.Create(Path.Combine(data,"desktop-smoke.png"))) await view.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png,screenshot);
                Shared.WriteJson(Path.Combine(data,"desktop-smoke.json"),proof);return;
            }
            await Task.Delay(200);
        }
        throw new Exception("Native window authentication timed out.");
    }
}
