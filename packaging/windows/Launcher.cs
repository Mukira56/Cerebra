using System;
using System.IO;
using System.Drawing;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Reflection;

[assembly: AssemblyTitle("AI Development HQ")]
[assembly: AssemblyVersion("0.2.1.0")]
[assembly: AssemblyDescription("Local AI development headquarters")]

internal static class Launcher {
    [STAThread] private static int Main(string[] args) {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        try {
            if(args.Length > 0) {
                string command = args[0];
                string[] forwarded = command == "--start-no-browser" ? new[]{"start", "--no-browser"} : command == "--stop" ? new[]{"stop"} : command == "--status" ? new[]{"status"} : command == "--doctor" ? new[]{"doctor"} : null;
                if(forwarded == null) throw new ArgumentException("Supported commands: --start-no-browser, --stop, --status, --doctor");
                int code; string output = Shared.Run(Shared.Root, forwarded, out code, 120); Console.Write(output); return code;
            }
            string data = (string)Shared.Config(Shared.Root)["data_dir"];
            string mutexName;
            using(var sha = System.Security.Cryptography.SHA256.Create()) mutexName = "Local\\AIHQ-" + BitConverter.ToString(sha.ComputeHash(System.Text.Encoding.UTF8.GetBytes(Shared.Full(data).ToLowerInvariant()))).Replace("-", "");
            bool fresh;
            using(var mutex = new Mutex(true, mutexName, out fresh)) {
                if(!fresh) { int code; string output=Shared.Run(Shared.Root,new[]{"start"},out code,30); if(code!=0) throw new Exception(output); return code; }
                Application.Run(new TrayContext());
            }
            return 0;
        } catch(Exception error) {
            if(args.Length > 0) Console.Error.WriteLine(error.Message);
            else MessageBox.Show(error.Message, "AI HQ", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}

internal sealed class TrayContext : ApplicationContext {
    private readonly NotifyIcon tray;
    private bool busy;
    internal TrayContext() {
        tray = new NotifyIcon { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath), Text = "AI Development HQ", Visible = true };
        var menu = new ContextMenuStrip();
        menu.Items.Add("Open dashboard",null,async delegate { await Execute(new[]{"start"}); });
        menu.Items.Add("Restart and open dashboard",null,async delegate { await Restart(); });
        menu.Items.Add("Diagnostics",null,async delegate { await Diagnostics(); });
        menu.Items.Add("Enable live agents...",null,async delegate { await EnableLive(); });
        menu.Items.Add("Open data folder",null,delegate { System.Diagnostics.Process.Start("explorer.exe", Shared.Quote((string)Shared.Config(Shared.Root)["data_dir"])); });
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Stop AI HQ and exit",null,async delegate { await StopAndExit(); });
        tray.ContextMenuStrip = menu;
        tray.DoubleClick += async delegate { await Execute(new[]{"start"}); };
        SynchronizationContext.SetSynchronizationContext(new WindowsFormsSynchronizationContext());
        Begin();
    }
    private async void Begin() {
        tray.ShowBalloonTip(2500,"AI HQ","Checking local tools and starting your private dashboard.",ToolTipIcon.Info);
        if(!await Execute(new[]{"start"})) { ExitThread(); return; }
        await Execute(new[]{"doctor"},false);
    }
    private async Task<bool> Execute(string[] command, bool report=true) {
        if(busy) return false; busy=true;
        try {
            int code=0; string output=await Task.Run(()=>Shared.Run(Shared.Root,command,out code,120));
            if(code!=0 && command[0]=="start" && output.Contains("PID identity does not match") && Shared.HasPreviousSource(Shared.Root)) {
                int previousCode=0;
                string previous=await Task.Run(()=>Shared.RunPreviousSource(Shared.Root,"status",out previousCode));
                if(previousCode==0) {
                    var status=Shared.Json.Deserialize<System.Collections.Generic.Dictionary<string,object>>(previous);
                    if(Convert.ToBoolean(status["running"])) {
                        int active=Convert.ToInt32(status["active_tasks"]);
                        string message="The previous source version of AI HQ is still running. Switch to this installed version now?\n\nYour projects and history will be preserved.";
                        if(active>0) message+="\n\n"+active+" task(s) are active. Switching interrupts them; you can explicitly resume them afterward.";
                        if(MessageBox.Show(message,"Switch to installed AI HQ",MessageBoxButtons.YesNo,MessageBoxIcon.Question)==DialogResult.Yes) {
                            string stopped=await Task.Run(()=>Shared.RunPreviousSource(Shared.Root,"stop",out previousCode));
                            if(previousCode!=0) throw new Exception(stopped);
                            output=await Task.Run(()=>Shared.Run(Shared.Root,command,out code,120));
                        } else return false;
                    }
                }
            }
            if(code!=0) { if(report) MessageBox.Show(output,"AI HQ",MessageBoxButtons.OK,MessageBoxIcon.Warning); return false; }
            return true;
        } catch(Exception error) { if(report) MessageBox.Show(error.Message,"AI HQ",MessageBoxButtons.OK,MessageBoxIcon.Error); return false; }
        finally { busy=false; }
    }
    private async Task Diagnostics() {
        if(busy) return; busy=true;
        try {
            int code=0; string text=await Task.Run(()=>Shared.Run(Shared.Root,new[]{"doctor"},out code,120));
            using(var form=new Form {Text="AI HQ diagnostics",Width=780,Height=550,StartPosition=FormStartPosition.CenterScreen}) {
                form.Controls.Add(new TextBox {Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Both,WordWrap=false,Dock=DockStyle.Fill,Font=new Font("Consolas",10),Text=text});form.ShowDialog();
            }
        } catch(Exception error) { MessageBox.Show(error.Message,"AI HQ diagnostics",MessageBoxButtons.OK,MessageBoxIcon.Error); }
        finally { busy=false; }
    }
    private bool ConfirmStop() {
        try {
        int code; string text=Shared.Run(Shared.Root,new[]{"status"},out code,20);
        if(code!=0) { MessageBox.Show(text,"AI HQ"); return false; }
        var status=Shared.Json.Deserialize<System.Collections.Generic.Dictionary<string,object>>(text);
        return Convert.ToInt32(status["active_tasks"])==0 || MessageBox.Show("Tasks are active. Stop them and preserve their files/history for explicit resume?","Stop AI HQ",MessageBoxButtons.YesNo,MessageBoxIcon.Question)==DialogResult.Yes;
        } catch(Exception error) { MessageBox.Show(error.Message,"AI HQ",MessageBoxButtons.OK,MessageBoxIcon.Warning); return false; }
    }
    private async Task Restart() { if(!busy && ConfirmStop() && await Execute(new[]{"stop"})) await Execute(new[]{"start"}); }
    private async Task StopAndExit() { if(!busy && ConfirmStop() && await Execute(new[]{"stop"})) ExitThread(); }
    private async Task EnableLive() {
        if(busy) return;
        string notice="Enable genuine Codex and Claude execution? Provider usage may be billable. CLI confinement is not full OS read isolation; outside-project reads remain possible. Only enable this for trusted projects. Every task still needs its own approval. No software or credentials will be installed.\n\nAI HQ must restart to change this policy.";
        if(MessageBox.Show(notice,"Enable live agents",MessageBoxButtons.YesNo,MessageBoxIcon.Question)!=DialogResult.Yes || !ConfirmStop()) return;
        if(!await Execute(new[]{"stop"})) return;
        if(!await Execute(new[]{"accept-cli-confinement","--acknowledge-residual-read-risk"})) return;
        if(!await Execute(new[]{"enable-live","--acknowledge-provider-usage"})) return;
        await Execute(new[]{"doctor"},false); await Execute(new[]{"start"});
    }
    protected override void ExitThreadCore() { tray.Visible=false; tray.Dispose(); base.ExitThreadCore(); }
}
