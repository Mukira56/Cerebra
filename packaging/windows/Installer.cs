using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Drawing;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("Cerebra Setup")]
[assembly: AssemblyVersion("0.10.0.0")]

internal sealed class InstallOptions {
    internal string Target=Shared.DefaultInstall, Data=Shared.DefaultData;
    internal int Port=8765;
    internal bool Quiet, Desktop=true, Shortcuts=true, TestRegistration;
    internal string Registration { get { return Shared.RegistryPath + (TestRegistration ? ".InstallerTest" : ""); } }
}
internal static class Setup {
    [STAThread] private static int Main(string[] args) {
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        var options=new InstallOptions();
        try {
            for(int i=0;i<args.Length;i++) {
                if(args[i]=="--quiet") options.Quiet=true;
                else if(args[i]=="--dir") options.Target=args[++i];
                else if(args[i]=="--data") options.Data=args[++i];
                else if(args[i]=="--port") options.Port=int.Parse(args[++i]);
                else if(args[i]=="--no-shortcuts") { options.Shortcuts=false; options.Desktop=false; }
                else if(args[i]=="--no-desktop") options.Desktop=false;
                else if(args[i]=="--test-registration") options.TestRegistration=true;
                else throw new ArgumentException("Unknown setup argument: " + args[i]);
            }
            if(options.Quiet) { Install(options,delegate(int value){}); Console.WriteLine("Cerebra installed: " + options.Target); }
            else Application.Run(new SetupForm(options));
            return 0;
        } catch(Exception error) {
            if(options.Quiet) Console.Error.WriteLine(error.Message);
            else MessageBox.Show(error.Message,"Cerebra Setup",MessageBoxButtons.OK,MessageBoxIcon.Error);
            return 1;
        }
    }
    internal static void Install(InstallOptions options, Action<int> progress) {
        options.Target=Shared.Full(options.Target); options.Data=Shared.Full(options.Data);
        if(options.Port<1024 || options.Port>65535) throw new ArgumentException("Port must be between 1024 and 65535.");
        if(options.Target==Path.GetPathRoot(options.Target).TrimEnd('\\') || options.Target==Shared.Full(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile))) throw new IOException("Choose a dedicated program directory.");
        if(options.Data==Path.GetPathRoot(options.Data).TrimEnd('\\') || options.Data==Shared.Full(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile)) || File.Exists(options.Data)) throw new IOException("Choose a dedicated data directory.");
        if(options.Target==options.Data || Shared.Inside(options.Data,options.Target) || Shared.Inside(options.Target,options.Data)) throw new IOException("Program files and project data must use separate, non-nested directories.");
        Shared.RejectLinks(options.Target); Shared.RejectLinks(options.Data); Shared.AssertStopped(options.Target);
        string marker=Path.Combine(options.Target,"aihq-install.json");
        if(Directory.Exists(options.Target) && Directory.GetFileSystemEntries(options.Target).Length>0 && (!File.Exists(marker) || (string)Shared.ReadJson(marker)["app_id"]!=Shared.AppId)) throw new IOException("The selected directory contains unrelated files. Choose an empty directory.");
        string parent=Path.GetDirectoryName(options.Target); Directory.CreateDirectory(parent);
        string stage=Path.Combine(parent,".aihq-stage-"+Guid.NewGuid().ToString("N")); Directory.CreateDirectory(stage);
        string backup=null; bool committed=false;
        try {
            using(Stream resource=Assembly.GetExecutingAssembly().GetManifestResourceStream("AIHQ.Payload.zip"))
            using(var archive=new ZipArchive(resource,ZipArchiveMode.Read)) {
                int count=0;
                foreach(var entry in archive.Entries) {
                    string name=entry.FullName.Replace('/',Path.DirectorySeparatorChar);
                    string destination=Path.GetFullPath(Path.Combine(stage,name));
                    if(!Shared.Inside(destination,stage) || Path.IsPathRooted(name) || name.IndexOf(':')>=0) throw new IOException("Invalid package entry.");
                    if(entry.Name.Length==0) {Directory.CreateDirectory(destination);continue;}
                    Directory.CreateDirectory(Path.GetDirectoryName(destination));
                    using(var input=entry.Open()) using(var output=new FileStream(destination,FileMode.CreateNew)) input.CopyTo(output);
                    count++;progress(Math.Min(85,count*85/Math.Max(1,archive.Entries.Count)));
                }
            }
            var release=Shared.ReadJson(Path.Combine(stage,"release-files.json"));
            var files=(Dictionary<string,object>)release["files"];
            foreach(var pair in files) {
                string file=Path.GetFullPath(Path.Combine(stage,pair.Key.Replace('/',Path.DirectorySeparatorChar)));
                if(!Shared.Inside(file,stage) || Shared.Hash(file)!=(string)pair.Value) throw new IOException("Package integrity check failed: "+pair.Key);
            }
            Shared.WriteJson(Path.Combine(stage,"desktop-settings.json"),new {app_id=Shared.AppId,version=Shared.Version,data_dir=options.Data,port=options.Port});
            var inventory=new List<string>(files.Keys);inventory.Add("release-files.json");inventory.Add("desktop-settings.json");inventory.Add("aihq-install.json");inventory.Add("previous-install.txt");
            string menu=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),options.TestRegistration?Shared.TestMenuName:Shared.MenuName);
            string desktop=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),Shared.ShortcutFile);
            Shared.WriteJson(Path.Combine(stage,"aihq-install.json"),new {app_id=Shared.AppId,version=Shared.Version,files=inventory,data_dir=options.Data,port=options.Port,registry=options.Registration,menu=options.Shortcuts?menu:"",desktop=options.Shortcuts&&options.Desktop?desktop:""});
            if(Directory.Exists(options.Target)) {backup=options.Target+".previous-"+Guid.NewGuid().ToString("N");Directory.Move(options.Target,backup);}
            Directory.Move(stage,options.Target);committed=true; Directory.CreateDirectory(options.Data);
            using(var key=Registry.CurrentUser.CreateSubKey(options.Registration)) {
                key.SetValue("DisplayName",options.TestRegistration?"Cerebra Installer Test":Shared.Product);key.SetValue("DisplayVersion",Shared.Version);
                key.SetValue("Publisher","Cerebra (Mukira56)");key.SetValue("InstallLocation",options.Target);key.SetValue("DisplayIcon",Path.Combine(options.Target,"AIHQ.exe"));
                key.SetValue("UninstallString",Shared.Quote(Path.Combine(options.Target,"Uninstall.exe")));key.SetValue("QuietUninstallString",Shared.Quote(Path.Combine(options.Target,"Uninstall.exe"))+" --quiet");
                key.SetValue("NoModify",1,RegistryValueKind.DWord);key.SetValue("NoRepair",1,RegistryValueKind.DWord);
            }
            Shared.RemoveLegacyShortcuts(options.Target,options.TestRegistration);
            if(options.Shortcuts) {
                Directory.CreateDirectory(menu);
                Shared.Shortcut(Path.Combine(menu,Shared.ShortcutFile),Path.Combine(options.Target,"AIHQ.exe"),"");
                Shared.Shortcut(Path.Combine(menu,Shared.UninstallShortcutFile),Path.Combine(options.Target,"Uninstall.exe"),"");
                if(options.Desktop) Shared.Shortcut(desktop,Path.Combine(options.Target,"AIHQ.exe"),"");
            }
            // Remove recorded program files from earlier copies; anything unknown stays in its backup folder.
            Shared.RemovePreviousCopies(options.Target);
            progress(100);
            if(backup!=null && Directory.Exists(backup)) File.WriteAllText(Path.Combine(options.Target,"previous-install.txt"),backup);
        } catch {
            if(!committed && backup!=null && !Directory.Exists(options.Target)) Directory.Move(backup,options.Target);
            throw;
        } finally {
            if(Directory.Exists(stage)) {Shared.RejectLinks(stage);if(Shared.Inside(stage,parent) && Path.GetFileName(stage).StartsWith(".aihq-stage-")) Directory.Delete(stage,true);}
        }
    }
}
internal sealed class SetupForm:Form {
    private readonly InstallOptions options;
    private readonly TextBox target=new TextBox(), data=new TextBox();
    private readonly CheckBox desktop=new CheckBox(), launch=new CheckBox();
    private readonly Button install=new Button();
    private readonly ProgressBar progress=new ProgressBar();
    private readonly Label state=new Label();
    internal SetupForm(InstallOptions value) {
        options=value;Text="Cerebra Setup";ClientSize=new Size(620,495);FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;StartPosition=FormStartPosition.CenterScreen;Font=new Font("Segoe UI",10);
        Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        Controls.Add(new PictureBox{Image=Icon.ToBitmap(),Location=new Point(30,25),Size=new Size(42,42),SizeMode=PictureBoxSizeMode.Zoom});
        Controls.Add(new Label{Text="Cerebra",Font=new Font("Segoe UI",22,FontStyle.Bold),Location=new Point(82,23),AutoSize=true});
        Controls.Add(new Label{Text="Version "+Shared.Version+"  |  Windows 10/11 x64  |  Installs for your account",Location=new Point(30,76),AutoSize=true,ForeColor=Color.DimGray});
        Controls.Add(new Label{Text="Program location",Location=new Point(30,121),AutoSize=true});target.SetBounds(30,146,555,29);target.Text=options.Target;Controls.Add(target);
        Controls.Add(new Label{Text="Project data and history (kept during uninstall)",Location=new Point(30,192),AutoSize=true});data.SetBounds(30,217,555,29);data.Text=options.Data;Controls.Add(data);
        Controls.Add(new Label{Text="Existing data stays in its current folder. No projects or credentials are bundled.\nGit and the coding CLIs are separate prerequisites; Python is included.",Location=new Point(30,265),Size=new Size(555,47),ForeColor=Color.DimGray});
        desktop.Text="Create a desktop shortcut";desktop.Checked=true;desktop.SetBounds(30,323,330,26);Controls.Add(desktop);
        launch.Text="Open Cerebra after installation";launch.Checked=!File.Exists(Path.Combine(options.Data,"server.json"));launch.SetBounds(30,350,330,26);Controls.Add(launch);
        state.SetBounds(30,389,555,24);state.Text="Close a running Cerebra or AI HQ before launching the installed version.";Controls.Add(state);
        progress.SetBounds(30,421,390,23);Controls.Add(progress);install.SetBounds(450,416,135,34);install.Text="Install";install.Click+=Install;Controls.Add(install);
        FormClosing+=delegate(object sender,FormClosingEventArgs args) {if(!install.Enabled)args.Cancel=true;};
    }
    private async void Install(object sender,EventArgs args) {
        install.Enabled=false;target.Enabled=false;data.Enabled=false;desktop.Enabled=false;launch.Enabled=false;
        options.Target=target.Text;options.Data=data.Text;options.Desktop=desktop.Checked;
        try {
            await Task.Run(()=>Setup.Install(options,p=>BeginInvoke((Action)(()=>{progress.Value=p;state.Text="Installing bundled application files...";}))));
            state.Text="Installed. Your project data was preserved.";install.Text="Finish";install.Enabled=true;install.Click-=Install;
            install.Click+=delegate {Close();};
            if(launch.Checked) System.Diagnostics.Process.Start(Path.Combine(options.Target,"AIHQ.exe"));
        } catch(Exception error) {
            MessageBox.Show(error.Message,"Cerebra Setup",MessageBoxButtons.OK,MessageBoxIcon.Error);state.Text="Installation did not finish.";install.Enabled=true;target.Enabled=true;data.Enabled=true;desktop.Enabled=true;launch.Enabled=true;
        }
    }
}
