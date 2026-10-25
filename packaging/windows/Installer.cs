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
[assembly: AssemblyVersion("0.16.0.0")]

internal sealed class InstallOptions {
    internal string Target=Shared.DefaultInstall, Data=Shared.DefaultData;
    internal int Port=8765;
    internal bool Quiet, Desktop=true, Shortcuts=true, TestRegistration, InstallGit;
    internal string Registration { get { return Shared.RegistryPath + (TestRegistration ? ".InstallerTest" : ""); } }
}
internal static class Prerequisites {
    internal const string GitPage="https://git-scm.com/download/win";
    // Git that actually runs: PATH, Git for Windows' recorded install folder, then its standard folders
    // (a fresh install isn't on this process's PATH yet).
    internal static string FindGit() {
        var candidates=new List<string>();
        foreach(string folder in (Environment.GetEnvironmentVariable("PATH")??"").Split(';')) { try { if(folder.Trim().Length>0) candidates.Add(Path.Combine(folder.Trim().Trim('"'),"git.exe")); } catch(ArgumentException) {} }
        foreach(var hive in new[]{Registry.CurrentUser,Registry.LocalMachine}) {
            try { using(var key=hive.OpenSubKey(@"Software\GitForWindows")) { string root=key==null?null:key.GetValue("InstallPath") as string; if(!string.IsNullOrEmpty(root)) candidates.Add(Path.Combine(root,"cmd","git.exe")); } }
            catch(Exception) {}
        }
        foreach(var root in new[]{Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs"),Environment.GetEnvironmentVariable("ProgramW6432")??"",
                                  Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86)})
            if(root.Length>0) candidates.Add(Path.Combine(root,"Git","cmd","git.exe"));
        foreach(var candidate in candidates) { try { if(File.Exists(candidate) && Works(candidate)) return candidate; } catch(ArgumentException) {} }
        return null;
    }
    // "git --version" must succeed; a leftover or broken git.exe doesn't count as installed.
    internal static bool Works(string git) {
        try {
            var info=new System.Diagnostics.ProcessStartInfo(git,"--version"){UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true};
            using(var process=System.Diagnostics.Process.Start(info)) {
                var output=process.StandardOutput.ReadToEndAsync(); process.StandardError.ReadToEndAsync();
                if(!process.WaitForExit(15000)) { try { process.Kill(); } catch(Exception) {} return false; }
                return process.ExitCode==0 && output.Result.StartsWith("git version");
            }
        } catch(Exception) { return false; }
    }
    internal const string WingetArguments="install --id Git.Git --exact --source winget --scope user --accept-package-agreements --accept-source-agreements";
    // Runs Windows Package Manager; returns its exit code, -1 when it couldn't start (cancelled or blocked), -2 on timeout.
    internal static int InstallGit(string winget,bool silent) {
        try {
            var info=new System.Diagnostics.ProcessStartInfo(winget,WingetArguments+(silent?" --silent --disable-interactivity":"")){UseShellExecute=!silent,CreateNoWindow=silent};
            using(var process=System.Diagnostics.Process.Start(info)) {
                if(!process.WaitForExit(1200000)) return -2;
                return process.ExitCode;
            }
        } catch(Exception) { return -1; }
    }
    internal static string Describe(int code) {
        if(code==-1) return "Windows Package Manager couldn't start (it may have been cancelled or blocked).";
        if(code==-2) return "Git setup took longer than 20 minutes and may still be running.";
        return "Windows Package Manager stopped with code "+code+". This usually means no internet connection, a cancelled permission request, or a download that failed.";
    }
    internal static string Json(string value) { return value==null?"null":"\""+value.Replace("\\","\\\\").Replace("\"","\\\"")+"\""; }
    internal static string FindWinget() {
        string apps=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Microsoft","WindowsApps","winget.exe");
        if(File.Exists(apps)) return apps;
        foreach(string folder in (Environment.GetEnvironmentVariable("PATH")??"").Split(';')) { try { string path=Path.Combine(folder.Trim(),"winget.exe"); if(folder.Trim().Length>0 && File.Exists(path)) return path; } catch(ArgumentException) {} }
        return null;
    }
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
                else if(args[i]=="--install-git") options.InstallGit=true;
                else if(args[i]=="--check-git") {
                    // Diagnostic for support: which Git and winget Setup would use (exit code 3 when Git is missing).
                    string git=Prerequisites.FindGit(), winget=Prerequisites.FindWinget();
                    Console.WriteLine("{\"git\": "+Prerequisites.Json(git)+", \"winget\": "+Prerequisites.Json(winget)+"}"); return git==null?3:0;
                }
                else throw new ArgumentException("Unknown setup argument: " + args[i]);
            }
            if(options.Quiet) {
                // Quiet installs (updates, tests) never install system software unless --install-git explicitly allows it.
                if(options.InstallGit && Prerequisites.FindGit()==null) {
                    string winget=Prerequisites.FindWinget();
                    if(winget==null) throw new IOException("Git is missing and Windows Package Manager (winget) isn't available. Install Git from "+Prerequisites.GitPage+" and run Setup again.");
                    int code=Prerequisites.InstallGit(winget,true);
                    string installed=Prerequisites.FindGit();
                    if(installed==null) throw new IOException("Git was not installed. "+Prerequisites.Describe(code));
                    Console.WriteLine("Git installed and verified: "+installed);
                }
                Install(options,delegate(int value){}); Console.WriteLine("Cerebra installed: " + options.Target);
                if(Prerequisites.FindGit()==null) Console.WriteLine("Note: Git is not installed. Cerebra needs it; install it from Cerebra's Required tools page or git-scm.com.");
            }
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
        Controls.Add(new Label{Text="Existing data stays in its current folder. Python is included.\nCerebra needs Git: Setup checks for it and can install it for you first.",Location=new Point(30,265),Size=new Size(555,47),ForeColor=Color.DimGray});
        desktop.Text="Create a desktop shortcut";desktop.Checked=true;desktop.SetBounds(30,323,330,26);Controls.Add(desktop);
        launch.Text="Open Cerebra after installation";launch.Checked=!File.Exists(Path.Combine(options.Data,"server.json"));launch.SetBounds(30,350,330,26);Controls.Add(launch);
        state.SetBounds(30,389,555,24);state.Text="Close a running Cerebra or AI HQ before launching the installed version.";Controls.Add(state);
        progress.SetBounds(30,421,390,23);Controls.Add(progress);install.SetBounds(450,416,135,34);install.Text="Install";install.Click+=Install;Controls.Add(install);
        FormClosing+=delegate(object sender,FormClosingEventArgs args) {if(!install.Enabled)args.Cancel=true;};
    }
    private void Unlock() { install.Enabled=true;target.Enabled=true;data.Enabled=true;desktop.Enabled=true;launch.Enabled=true; }
    // Git first: Cerebra keeps every task in Git, so offer to install it (with Windows' own installer) before installing Cerebra.
    private async Task<bool> EnsureGit() {
        if(Prerequisites.FindGit()!=null) return true;
        var answer=MessageBox.Show("Cerebra needs Git, and it isn't installed on this computer yet.\n\n"+
            "Git is free. It keeps every version of your projects safe, and Cerebra uses it for every task so your work can always be checked and undone.\n\n"+
            "Install Git now? This needs an internet connection. Windows Package Manager downloads Git for Windows from its official source "+
            "and accepts the Git package's licence (GPL v2) and the winget source agreement on your behalf. Windows may ask for your permission.\n\n"+
            "Yes: install Git, then Cerebra.\nNo: install Cerebra only (it will remind you to add Git).\nCancel: stop for now.",
            "Cerebra needs Git",MessageBoxButtons.YesNoCancel,MessageBoxIcon.Information);
        if(answer==DialogResult.No) return true;
        if(answer!=DialogResult.Yes) return false;
        string winget=Prerequisites.FindWinget();
        if(winget==null) {
            try { System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(Prerequisites.GitPage){UseShellExecute=true}); } catch(Exception) {}
            MessageBox.Show("Windows' installer tool (winget) isn't available, so the official Git download page opened in your browser.\n\nInstall Git from there (the default options are fine), then press Install here again. Setup finds it without restarting.","Install Git",MessageBoxButtons.OK,MessageBoxIcon.Information);
            return false;
        }
        state.Text="Installing Git… a window shows its progress. Approve Windows' permission request.";
        int code=await Task.Run(()=>Prerequisites.InstallGit(winget,false));
        state.Text="Checking that Git works…";
        string git=await Task.Run(()=>Prerequisites.FindGit());
        if(git!=null) { state.Text="Git is installed and working. Installing Cerebra…"; return true; }
        return MessageBox.Show("Git didn't finish installing. "+Prerequisites.Describe(code)+"\n\nPress OK to install Cerebra now and add Git later from its Required tools page, or Cancel to try again.","Git was not installed",MessageBoxButtons.OKCancel,MessageBoxIcon.Warning)==DialogResult.OK;
    }
    private async void Install(object sender,EventArgs args) {
        install.Enabled=false;target.Enabled=false;data.Enabled=false;desktop.Enabled=false;launch.Enabled=false;
        options.Target=target.Text;options.Data=data.Text;options.Desktop=desktop.Checked;
        if(!await EnsureGit()) { state.Text="Setup paused. Press Install when you're ready."; Unlock(); return; }
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
