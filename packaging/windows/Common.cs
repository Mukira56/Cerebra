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
    internal const string Version = "0.2.0";
    internal const string RegistryPath = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\AIDevelopmentHQ";
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
                    if(Inside(image, root)) throw new InvalidOperationException("AI HQ is running. Use its tray menu to stop and exit before installing or uninstalling.");
                } catch(System.ComponentModel.Win32Exception) {} catch(InvalidOperationException exception) {
                    if(exception.Message.StartsWith("AI HQ is running")) throw;
                }
            }
        }
    }
    internal static string Run(string root, string[] arguments, out int code, int seconds) {
        var configuration = Config(root);
        var command = new StringBuilder("-X utf8 -m ai_hq.manage");
        foreach(string argument in arguments) command.Append(" " + Quote(argument));
        if(Array.IndexOf(arguments, "--port") < 0) command.Append(" --port " + Convert.ToInt32(configuration["port"]));
        var info = new ProcessStartInfo(Python(root), command.ToString()) { WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
        info.EnvironmentVariables["AIHQ_DATA_DIR"] = (string)configuration["data_dir"];
        info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
        info.EnvironmentVariables.Remove("PYTHONPATH");
        using(var process = Process.Start(info)) {
            var stdout = process.StandardOutput.ReadToEndAsync(); var stderr = process.StandardError.ReadToEndAsync();
            if(!process.WaitForExit(seconds * 1000)) throw new TimeoutException("AI HQ did not respond in time. Check its data folder before retrying; no unrelated process was terminated.");
            System.Threading.Tasks.Task.WaitAll(stdout, stderr);
            code = process.ExitCode; return stdout.Result + stderr.Result;
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
    internal static void RemoveShortcut(string path, string expected) {
        if(!File.Exists(path)) return;
        Type type=Type.GetTypeFromProgID("WScript.Shell");object shell=Activator.CreateInstance(type);
        object link=type.InvokeMember("CreateShortcut",System.Reflection.BindingFlags.InvokeMethod,null,shell,new object[]{path});
        string target=Convert.ToString(link.GetType().InvokeMember("TargetPath",System.Reflection.BindingFlags.GetProperty,null,link,null));
        if(!string.IsNullOrEmpty(target) && string.Equals(Full(target),Full(expected),StringComparison.OrdinalIgnoreCase)) File.Delete(path);
        System.Runtime.InteropServices.Marshal.FinalReleaseComObject(link);System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell);
    }
}
