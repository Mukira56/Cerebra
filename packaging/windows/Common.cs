using System;
using System.IO;
using System.Diagnostics;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Win32;

internal static class Shared {
    internal const string AppId = "AIDevelopmentHQ";
    internal const string Version = "0.12.0";
    internal const string RegistryPath = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\AIDevelopmentHQ";
    // Product name. Internal ids (AppId, registry key, AIHQ.exe, install/data folders) keep their pre-rename
    // values so upgrades from "AI HQ" replace the same installation and keep the same data.
    internal const string Product = "Cerebra";
    internal const string MenuName = "Cerebra", TestMenuName = "Cerebra InstallerTest", ShortcutFile = "Cerebra.lnk", UninstallShortcutFile = "Uninstall Cerebra.lnk";
    internal const string LegacyMenuName = "AI Development HQ", LegacyTestMenuName = "AI HQ InstallerTest", LegacyShortcutFile = "AI Development HQ.lnk", LegacyUninstallShortcutFile = "Uninstall AI HQ.lnk";
    internal static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 16777216 };
    internal static string Root { get { return AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar); } }
    internal static string DefaultInstall { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "AI HQ"); } }
    internal static string DefaultData {
        get {
            string previous = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "AI-Development-HQ", "data");
            return File.Exists(Path.Combine(previous, "hq.sqlite3")) ? previous : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AI HQ", "data");
        }
    }
    internal static string Full(string path) { return Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar); }
    internal static bool Inside(string path, string root) { return Full(path).StartsWith(Full(root) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase); }
    internal static void RejectLinks(string path) {
        DirectoryInfo part = new DirectoryInfo(Full(path));
        while(part != null) {
            if(part.Exists && (part.Attributes & FileAttributes.ReparsePoint) != 0) throw new IOException("Linked directories are not supported: " + part.FullName);
            part = part.Parent;
        }
    }
    internal static string Quote(string value) {
        // CommandLineToArgvW quoting, including runs of backslashes before quotes.
        StringBuilder result = new StringBuilder("\""); int slash = 0;
        foreach(char c in value) {
            if(c == '\\') { slash++; continue; }
            if(c == '"') { result.Append('\\', slash * 2 + 1); result.Append(c); slash = 0; continue; }
            result.Append('\\', slash); slash = 0; result.Append(c);
        }
        result.Append('\\', slash * 2); return result.Append('"').ToString();
    }
    internal static string Hash(string path) { using(var sha = SHA256.Create()) using(var file = File.OpenRead(path)) return BitConverter.ToString(sha.ComputeHash(file)).Replace("-", "").ToLowerInvariant(); }
    internal static Dictionary<string, object> ReadJson(string path) { return Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(path, Encoding.UTF8)); }
    internal static void WriteJson(string path, object value) { File.WriteAllText(path, Json.Serialize(value), new UTF8Encoding(false)); }
    internal static Dictionary<string, object> Config(string root) { return ReadJson(Path.Combine(root, "desktop-settings.json")); }
    internal static string Python(string root) { return Path.Combine(root, "runtime", "python.exe"); }
    internal static void AssertStopped(string root) {
        foreach(var process in Process.GetProcesses()) {
            using(process) {
                try {
                    if(process.Id == Process.GetCurrentProcess().Id) continue;
                    string name = process.ProcessName.ToLowerInvariant();
                    if(name != "python" && name != "pythonw" && name != "aihq") continue;
                    string image = process.MainModule.FileName;
                    if(Inside(image, root)) throw new InvalidOperationException("Cerebra is running. Use its tray menu to stop and exit before installing or uninstalling.");
                } catch(System.ComponentModel.Win32Exception) {} catch(InvalidOperationException exception) {
                    if(exception.Message.StartsWith("Cerebra is running")) throw;
                }
            }
        }
    }
    internal static string Run(string root, string[] arguments, out int code, int seconds) {
        return RunPython(root, Python(root), arguments, out code, seconds);
    }
    internal static bool HasPreviousSource(string root) {
        string source = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "AI-Development-HQ");
        return string.Equals(Full((string)Config(root)["data_dir"]), Full(Path.Combine(source,"data")), StringComparison.OrdinalIgnoreCase)
            && File.Exists(Path.Combine(source,".venv","Scripts","python.exe")) && File.Exists(Path.Combine(source,"ai_hq","manage.py"));
    }
    internal static string RunPreviousSource(string root, string command, out int code) {
        if(!HasPreviousSource(root) || (command!="status" && command!="stop")) throw new InvalidOperationException("The previous source installation could not be verified. Stop it from its own tray menu before retrying.");
        string source = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "AI-Development-HQ");
        RejectLinks(source); RejectLinks(Path.Combine(source,".venv","Scripts"));
        string inspect="import json,sqlite3; from ai_hq.manage import owned_process; from ai_hq.config import Settings; s=Settings(); running=bool(owned_process(s)); db=sqlite3.connect(s.db_path.as_uri()+'?mode=ro',uri=True); active=db.execute(\"select count(*) from tasks where state in ('RUNNING','VERIFYING','REVIEWING','NEEDS_CHANGES')\").fetchone()[0]; db.close(); print(json.dumps(dict(running=running,active_tasks=active)))";
        return RunPython(source,Path.Combine(source,".venv","Scripts","python.exe"),command=="status"?new string[0]:new[]{command},out code,30,root,command=="status"?inspect:null);
    }
    private static string RunPython(string root, string python, string[] arguments, out int code, int seconds, string configurationRoot=null, string inspect=null) {
        var configuration = Config(configurationRoot ?? root);
        var command = new StringBuilder(inspect==null?"-X utf8 -m ai_hq.manage":"-X utf8 -c "+Quote(inspect));
        foreach(string argument in arguments) command.Append(" " + Quote(argument));
        if(Array.IndexOf(arguments, "--port") < 0) command.Append(" --port " + Convert.ToInt32(configuration["port"]));
        var info = new ProcessStartInfo(python, command.ToString()) { WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
        info.EnvironmentVariables["AIHQ_DATA_DIR"] = (string)configuration["data_dir"];
        info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
        info.EnvironmentVariables.Remove("PYTHONPATH");
        using(var process = Process.Start(info)) {
            var stdout = process.StandardOutput.ReadToEndAsync(); var stderr = process.StandardError.ReadToEndAsync();
            if(!process.WaitForExit(seconds * 1000)) throw new TimeoutException("Cerebra did not respond in time. Check its data folder before retrying; no unrelated process was terminated.");
            System.Threading.Tasks.Task.WaitAll(stdout, stderr);
            code = process.ExitCode; return stdout.Result + stderr.Result;
        }
    }
    // Delete only the files an install inventory lists, then directories left empty. Unknown files survive.
    internal static void RemoveRecorded(string root, System.Collections.IEnumerable entries) {
        var paths=new List<string>();var directories=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach(object entry in entries) {
            string file=Path.GetFullPath(Path.Combine(root,Convert.ToString(entry).Replace('/',Path.DirectorySeparatorChar)));
            if(!Inside(file,root))throw new IOException("Unsafe uninstall inventory; no files were removed.");
            RejectLinks(Path.GetDirectoryName(file));
            if(File.Exists(file) && (File.GetAttributes(file)&FileAttributes.ReparsePoint)!=0)throw new IOException("A program file is a link; inspect it manually before uninstall.");
            paths.Add(file);DirectoryInfo parent=new DirectoryInfo(Path.GetDirectoryName(file));
            while(parent!=null && Inside(parent.FullName,root)){directories.Add(parent.FullName);parent=parent.Parent;}
        }
        foreach(string path in paths)if(File.Exists(path)){File.SetAttributes(path,FileAttributes.Normal);File.Delete(path);}
        var ordered=new List<string>(directories);ordered.Sort((a,b)=>b.Length.CompareTo(a.Length));
        foreach(string directory in ordered)if(Directory.Exists(directory)&&Directory.GetFileSystemEntries(directory).Length==0)Directory.Delete(directory);
        if(Directory.Exists(root)&&Directory.GetFileSystemEntries(root).Length==0)Directory.Delete(root);
    }
    // Upgrades move the old program folder aside as "<target>.previous-<guid>". Once the new copy is in place,
    // remove each verified backup's recorded files; a backup holding unknown files keeps only those.
    internal static void RemovePreviousCopies(string target) {
        string parent=Path.GetDirectoryName(target), prefix=Path.GetFileName(target)+".previous-";
        foreach(string folder in Directory.GetDirectories(parent,prefix+"*")) {
            try {
                if(Path.GetFileName(folder).Length!=prefix.Length+32) continue;
                RejectLinks(folder);
                var record=ReadJson(Path.Combine(folder,"aihq-install.json"));
                if((string)record["app_id"]!=AppId) continue;
                AssertStopped(folder);
                RemoveRecorded(Full(folder),(System.Collections.IEnumerable)record["files"]);
            } catch(Exception) {} // A backup that cannot be verified or fully removed is left in place.
        }
    }
    internal static void Shortcut(string path, string target, string arguments) {
        Type type = Type.GetTypeFromProgID("WScript.Shell"); object shell = Activator.CreateInstance(type);
        object shortcut = type.InvokeMember("CreateShortcut", System.Reflection.BindingFlags.InvokeMethod, null, shell, new object[] {path});
        Type link = shortcut.GetType();
        string existing = Convert.ToString(link.InvokeMember("TargetPath", System.Reflection.BindingFlags.GetProperty, null, shortcut, null));
        if(File.Exists(path) && !string.IsNullOrEmpty(existing) && !string.Equals(Full(existing),Full(target),StringComparison.OrdinalIgnoreCase)) {
            System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shortcut);System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell);return;
        }
        link.InvokeMember("TargetPath", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[]{target});
        link.InvokeMember("Arguments", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[]{arguments});
        link.InvokeMember("WorkingDirectory", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[]{Path.GetDirectoryName(target)});
        link.InvokeMember("IconLocation", System.Reflection.BindingFlags.SetProperty, null, shortcut, new object[]{target + ",0"});
        link.InvokeMember("Save", System.Reflection.BindingFlags.InvokeMethod, null, shortcut, new object[0]);
        System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shortcut); System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell);
    }
    // Shortcuts made by pre-rename versions, removed only when they point at this installation.
    internal static void RemoveLegacyShortcuts(string root, bool test) {
        string menu=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs),test?LegacyTestMenuName:LegacyMenuName);
        RemoveShortcut(Path.Combine(menu,LegacyShortcutFile),Path.Combine(root,"AIHQ.exe"));
        RemoveShortcut(Path.Combine(menu,LegacyUninstallShortcutFile),Path.Combine(root,"Uninstall.exe"));
        if(Directory.Exists(menu) && Directory.GetFileSystemEntries(menu).Length==0) Directory.Delete(menu);
        if(!test) RemoveShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),LegacyShortcutFile),Path.Combine(root,"AIHQ.exe"));
    }
    internal static void RemoveShortcut(string path, string expected) {
        if(!File.Exists(path)) return;
        Type type=Type.GetTypeFromProgID("WScript.Shell");object shell=Activator.CreateInstance(type);
        object link=type.InvokeMember("CreateShortcut",System.Reflection.BindingFlags.InvokeMethod,null,shell,new object[]{path});
        string target=Convert.ToString(link.GetType().InvokeMember("TargetPath",System.Reflection.BindingFlags.GetProperty,null,link,null));
        if(!string.IsNullOrEmpty(target) && string.Equals(Full(target),Full(expected),StringComparison.OrdinalIgnoreCase)) File.Delete(path);
        System.Runtime.InteropServices.Marshal.FinalReleaseComObject(link);System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell);
    }
}
