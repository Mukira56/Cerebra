using System;
using System.IO;
using System.Diagnostics;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("Uninstall AI Development HQ")]
[assembly: AssemblyVersion("0.4.0.0")]

internal static class Uninstall {
    [STAThread] private static int Main(string[] args) {
        bool quiet=Array.IndexOf(args,"--quiet")>=0;
        try {
            if(args.Length>0 && args[0]=="--remove") {
                string target=Shared.Full(args[1]);int parent=int.Parse(args[2]);
                try {using(var previous=Process.GetProcessById(parent)) if(!previous.WaitForExit(15000)) throw new IOException("The original uninstaller has not exited.");}catch(ArgumentException){}
                Remove(target);
                if(!quiet) MessageBox.Show("AI HQ was uninstalled. Project files, task history and logs were kept.","AI HQ");
                return 0;
            }
            string root=Shared.Root;Validate(root);Shared.AssertStopped(root);
            if(!quiet && MessageBox.Show("Remove AI HQ program files and shortcuts? Your project data, task history and logs will be kept.","Uninstall AI HQ",MessageBoxButtons.YesNo,MessageBoxIcon.Question)!=DialogResult.Yes)return 0;
            string helper=Path.Combine(Path.GetTempPath(),"AIHQ-Uninstall-"+Guid.NewGuid().ToString("N")+".exe");
            File.Copy(Assembly.GetExecutingAssembly().Location,helper,false);
            Process.Start(new ProcessStartInfo(helper,"--remove "+Shared.Quote(root)+" "+Process.GetCurrentProcess().Id+(quiet?" --quiet":"")){UseShellExecute=false,CreateNoWindow=true});
            return 0;
        }catch(Exception error){if(quiet)Console.Error.WriteLine(error.Message);else MessageBox.Show(error.Message,"AI HQ uninstall",MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;}
    }
    private static Dictionary<string,object> Validate(string root) {
        Shared.RejectLinks(root);
        var record=Shared.ReadJson(Path.Combine(root,"aihq-install.json"));
        if((string)record["app_id"]!=Shared.AppId)throw new IOException("This directory is not an AI HQ installation.");
        string registration=(string)record["registry"];
        if(registration!=Shared.RegistryPath && registration!=Shared.RegistryPath+".InstallerTest")throw new IOException("Invalid AI HQ registration.");
        using(var key=Registry.CurrentUser.OpenSubKey(registration)) {
            if(key==null || !string.Equals(Shared.Full(Convert.ToString(key.GetValue("InstallLocation"))),root,StringComparison.OrdinalIgnoreCase)) throw new IOException("Installation registration does not match; no files were removed.");
        }
        string data=Shared.Full((string)record["data_dir"]);
        if(root==data || Shared.Inside(data,root) || Shared.Inside(root,data))throw new IOException("Program/data boundary is invalid; no files were removed.");
        return record;
    }
    private static void Remove(string root) {
        var record=Validate(root);Shared.AssertStopped(root);
        var paths=new List<string>();var directories=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach(object entry in (IEnumerable)record["files"]) {
            string file=Path.GetFullPath(Path.Combine(root,Convert.ToString(entry).Replace('/',Path.DirectorySeparatorChar)));
            if(!Shared.Inside(file,root))throw new IOException("Unsafe uninstall inventory; no files were removed.");
            Shared.RejectLinks(Path.GetDirectoryName(file));
            if(File.Exists(file) && (File.GetAttributes(file)&FileAttributes.ReparsePoint)!=0)throw new IOException("A program file is a link; inspect it manually before uninstall.");
            paths.Add(file);DirectoryInfo parent=new DirectoryInfo(Path.GetDirectoryName(file));
            while(parent!=null && Shared.Inside(parent.FullName,root)){directories.Add(parent.FullName);parent=parent.Parent;}
        }
        string menu=(string)record["menu"], desktop=(string)record["desktop"];
        string expectedMenu=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),(string)record["registry"]==Shared.RegistryPath?"AI Development HQ":"AI HQ InstallerTest");
        if(!string.IsNullOrEmpty(menu) && string.Equals(menu,expectedMenu,StringComparison.OrdinalIgnoreCase)) {
            Shared.RemoveShortcut(Path.Combine(menu,"AI Development HQ.lnk"),Path.Combine(root,"AIHQ.exe"));
            Shared.RemoveShortcut(Path.Combine(menu,"Uninstall AI HQ.lnk"),Path.Combine(root,"Uninstall.exe"));
            if(Directory.Exists(menu) && Directory.GetFileSystemEntries(menu).Length==0)Directory.Delete(menu);
        }
        string expectedDesktop=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),"AI Development HQ.lnk");
        if(desktop==expectedDesktop)Shared.RemoveShortcut(desktop,Path.Combine(root,"AIHQ.exe"));
        foreach(string path in paths)if(File.Exists(path)){File.SetAttributes(path,FileAttributes.Normal);File.Delete(path);}
        var ordered=new List<string>(directories);ordered.Sort((a,b)=>b.Length.CompareTo(a.Length));
        foreach(string directory in ordered)if(Directory.Exists(directory)&&Directory.GetFileSystemEntries(directory).Length==0)Directory.Delete(directory);
        if(Directory.Exists(root)&&Directory.GetFileSystemEntries(root).Length==0)Directory.Delete(root);
        Registry.CurrentUser.DeleteSubKeyTree((string)record["registry"],false);
    }
}
