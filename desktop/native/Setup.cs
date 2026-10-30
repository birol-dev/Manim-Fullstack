// Per-user Windows installer and uninstaller for Manim Studio.
// desktop/scripts/build_installer.py appends the payload after this stub:
// [stub exe][zip][8-byte little-endian payload length][8-byte "MSETUP01" magic].
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

static class Program
{
    public const string StudioVersion = "@@VERSION@@";

    [STAThread]
    static int Main(string[] args)
    {
        ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072;
        Options options;
        try
        {
            options = Options.Parse(args);
        }
        catch (Exception error)
        {
            if (!HasSilentSwitch(args))
                MessageBox.Show("Setup could not understand its options. " + error.Message,
                                "Manim Studio", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return ExitCodes.Failed;
        }
        if (options.Uninstall)
        {
            // The installed Uninstall.exe cannot delete its own folder while running.
            if (!options.FromTemp) return Uninstaller.Launch(options);
            return Uninstaller.Run(options);
        }
        if (options.Silent) return Installer.RunSilent(options);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new SetupForm(options));
        return ExitCodes.Ok;
    }

    static bool HasSilentSwitch(string[] args)
    {
        foreach (string argument in args)
            if (argument.Equals("/s", StringComparison.OrdinalIgnoreCase) ||
                argument.Equals("/silent", StringComparison.OrdinalIgnoreCase)) return true;
        return false;
    }
}

static class ExitCodes
{
    public const int Ok = 0;
    public const int Failed = 1;
    public const int AppRunning = 2;
    public const int NoSpace = 3;
}

static class Messages
{
    public const string AppRunning =
        "Manim Studio is still running, or an AI app is using it. Close them, then choose Retry.";
}

sealed class Options
{
    public bool Silent;
    public bool Uninstall;
    public bool NoWebView2;
    public bool FromTemp;
    public bool DesktopShortcut = true;
    public string Directory;

    public static Options Parse(string[] args)
    {
        Options options = new Options();
        for (int index = 0; index < args.Length; index++)
        {
            string argument = args[index];
            string lowered = argument.ToLowerInvariant();
            if (lowered == "/s" || lowered == "/silent") options.Silent = true;
            else if (lowered == "/uninstall") options.Uninstall = true;
            else if (lowered == "/nowebview2") options.NoWebView2 = true;
            else if (lowered == "/fromtemp") options.FromTemp = true;
            else if (lowered.StartsWith("/dir:")) options.Directory = argument.Substring(5);
            else if (lowered.StartsWith("/dir=")) options.Directory = argument.Substring(5);
            else if (lowered == "/dir" && index + 1 < args.Length) options.Directory = args[++index];
        }
        if (options.Directory != null)
            options.Directory = Path.GetFullPath(options.Directory.Trim('"'));
        return options;
    }

    public string InstallDir { get { return Directory ?? Paths.DefaultInstallDir; } }

    // Tests pass /dir:, so they must not touch the real uninstall entry.
    public string UninstallKeyName
    {
        get { return Directory != null ? Paths.TestUninstallKey : Paths.DefaultUninstallKey; }
    }
}

static class Paths
{
    public const string AppExe = "Manim Studio.exe";
    public const string UninstallExe = "Uninstall.exe";
    public const string DefaultUninstallKey = "ManimStudio";
    public const string TestUninstallKey = "ManimStudio-Test";

    public static string LocalAppData
    {
        get { return Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData); }
    }

    public static string DefaultInstallDir
    {
        get { return Path.Combine(LocalAppData, "Programs", "ManimStudio"); }
    }

    // The installed app keeps using this folder for videos and projects.
    public static string DataDir
    {
        get { return Path.Combine(LocalAppData, "ManimStudio"); }
    }

    public static string StartMenuShortcut
    {
        get
        {
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                                "Microsoft", "Windows", "Start Menu", "Programs", "Manim Studio.lnk");
        }
    }

    public static string DesktopShortcut
    {
        get
        {
            return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                                "Manim Studio.lnk");
        }
    }
}

sealed class InstallResult
{
    public bool Success;
    public int ExitCode;
    public string Message;
    public string WebView2Message;
    public bool WebView2Missing;
    public string InstallDir;
}

static class Installer
{
    public static int RunSilent(Options options)
    {
        InstallResult result = Install(options, delegate { });
        return result.Success ? ExitCodes.Ok : result.ExitCode;
    }

    public static InstallResult Install(Options options, Action<string> status)
    {
        InstallResult result = new InstallResult();
        result.InstallDir = options.InstallDir;
        string target = options.InstallDir;
        try
        {
            status("Checking your PC...");
            if (Processes.IsRunningFrom(target))
            {
                result.ExitCode = ExitCodes.AppRunning;
                result.Message = Messages.AppRunning;
                return result;
            }

            string fullTarget = Path.GetFullPath(target);
            string parent = Path.GetDirectoryName(fullTarget.TrimEnd(Path.DirectorySeparatorChar));
            if (String.IsNullOrEmpty(parent) || String.Equals(parent, fullTarget, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Choose a folder for Manim Studio, not a whole drive.");

            long expanded = 0;
            using (Stream payload = Payload.Open())
            using (ZipArchive archive = new ZipArchive(payload, ZipArchiveMode.Read, true))
            {
                foreach (ZipArchiveEntry entry in archive.Entries)
                    if (!String.IsNullOrEmpty(entry.Name)) expanded += entry.Length;
            }
            long needed = expanded + new FileInfo(Application.ExecutablePath).Length + 64L * 1024L * 1024L;
            if (Directory.Exists(target)) needed += expanded; // the old copy stays until the swap finishes
            status("Checking free space...");
            try
            {
                DriveInfo drive = new DriveInfo(Path.GetPathRoot(fullTarget));
                if (drive.AvailableFreeSpace < needed)
                {
                    result.ExitCode = ExitCodes.NoSpace;
                    result.Message = String.Format(
                        "There isn't enough free space. Manim Studio needs about {0} MB and this drive has {1} MB free. " +
                        "Free some space, then choose Install again.",
                        needed / (1024 * 1024), drive.AvailableFreeSpace / (1024 * 1024));
                    return result;
                }
            }
            catch (ArgumentException)
            {
                // Network shares do not expose DriveInfo; let the extraction report a real failure.
            }
            catch (IOException)
            {
            }

            string token = Guid.NewGuid().ToString("N");
            string staging = Path.Combine(parent, ".manim-studio-" + token + ".new");
            string backup = Path.Combine(parent, ".manim-studio-" + token + ".old");
            Directory.CreateDirectory(parent);
            Directory.CreateDirectory(staging);
            try
            {
                status("Installing Manim Studio...");
                Extract(staging, expanded, status);
                // The uninstall stub is part of the new tree, so the swap installs everything at once.
                WriteUninstallStub(Path.Combine(staging, Paths.UninstallExe));
                if (Processes.IsRunningFrom(target))
                {
                    result.ExitCode = ExitCodes.AppRunning;
                    result.Message = Messages.AppRunning;
                    return result;
                }
                status("Finishing the install...");
                try
                {
                    Swap(staging, target, backup);
                }
                catch (IOException)
                {
                    result.ExitCode = ExitCodes.AppRunning;
                    result.Message = Messages.AppRunning;
                    return result;
                }
                catch (UnauthorizedAccessException)
                {
                    result.ExitCode = ExitCodes.AppRunning;
                    result.Message = Messages.AppRunning;
                    return result;
                }
            }
            finally
            {
                TryDeleteDirectory(staging);
            }

            if (options.Directory == null)
            {
                status("Adding shortcuts...");
                string exe = Path.Combine(target, Paths.AppExe);
                Shortcut.Create(Paths.StartMenuShortcut, exe, target);
                if (options.DesktopShortcut) Shortcut.Create(Paths.DesktopShortcut, exe, target);
            }

            status("Registering Manim Studio...");
            UninstallEntry.Write(options.UninstallKeyName, target);

            if (!options.NoWebView2)
            {
                string problem = WebView2.Ensure(status);
                if (problem != null)
                {
                    result.WebView2Missing = true;
                    result.WebView2Message = problem;
                }
            }

            result.Success = true;
            result.ExitCode = ExitCodes.Ok;
            result.Message = "Manim Studio is installed.";
            return result;
        }
        catch (Exception error)
        {
            result.Success = false;
            result.ExitCode = ExitCodes.Failed;
            result.Message = "Manim Studio could not be installed. " + error.Message;
            return result;
        }
    }

    static void Extract(string staging, long expanded, Action<string> status)
    {
        string rootWithSeparator = staging.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                                   + Path.DirectorySeparatorChar;
        long written = 0;
        int lastPercent = -1;
        using (Stream payload = Payload.Open())
        using (ZipArchive archive = new ZipArchive(payload, ZipArchiveMode.Read, true))
        {
            foreach (ZipArchiveEntry entry in archive.Entries)
            {
                if (String.IsNullOrEmpty(entry.Name)) continue;
                // Zip-slip guard: every extracted path must stay inside the staging folder.
                string destination = Path.GetFullPath(Path.Combine(
                    staging, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
                if (!destination.StartsWith(rootWithSeparator, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException(
                        "This installer contains an unsafe file path and was stopped.");
                Directory.CreateDirectory(Path.GetDirectoryName(destination));
                using (Stream input = entry.Open())
                using (FileStream output = new FileStream(destination, FileMode.Create, FileAccess.Write, FileShare.None))
                    input.CopyTo(output);
                written += entry.Length;
                int percent = expanded > 0 ? (int)(written * 100 / expanded) : 0;
                if (percent != lastPercent)
                {
                    lastPercent = percent;
                    status("Installing Manim Studio... " + percent + "%");
                }
            }
        }
    }

    // Uninstall.exe only needs the setup stub: everything before the payload is the whole program.
    static void WriteUninstallStub(string destination)
    {
        long stubLength = Payload.StartOffset();
        using (FileStream input = new FileStream(Application.ExecutablePath, FileMode.Open, FileAccess.Read,
                                                 FileShare.ReadWrite | FileShare.Delete))
        using (FileStream output = new FileStream(destination, FileMode.Create, FileAccess.Write, FileShare.None))
        {
            byte[] buffer = new byte[81920];
            long remaining = stubLength;
            while (remaining > 0)
            {
                int read = input.Read(buffer, 0, (int)Math.Min(buffer.Length, remaining));
                if (read <= 0)
                    throw new InvalidDataException("This installer file is incomplete. Download it again.");
                output.Write(buffer, 0, read);
                remaining -= read;
            }
        }
    }

    static void Swap(string staging, string target, string backup)
    {
        bool moved = false;
        if (Directory.Exists(target))
        {
            Directory.Move(target, backup);
            moved = true;
        }
        try
        {
            Directory.Move(staging, target);
        }
        catch
        {
            if (!Directory.Exists(target) && moved && Directory.Exists(backup))
                Directory.Move(backup, target);
            throw;
        }
        TryDeleteDirectory(backup);
    }

    public static void TryDeleteDirectory(string folder)
    {
        if (String.IsNullOrEmpty(folder) || !Directory.Exists(folder)) return;
        for (int attempt = 0; attempt < 5; attempt++)
        {
            try
            {
                Directory.Delete(folder, true);
                return;
            }
            catch (IOException)
            {
                Thread.Sleep(200);
            }
            catch (UnauthorizedAccessException)
            {
                Thread.Sleep(200);
            }
        }
    }

    public static void TryDeleteFile(string path)
    {
        try { if (File.Exists(path)) File.Delete(path); }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }
}

static class Payload
{
    static readonly byte[] Magic = Encoding.ASCII.GetBytes("MSETUP01");

    static FileStream OpenFile()
    {
        return new FileStream(Application.ExecutablePath, FileMode.Open, FileAccess.Read,
                              FileShare.ReadWrite | FileShare.Delete);
    }

    static void Locate(FileStream file, out long start, out long length)
    {
        long size = file.Length;
        int scan = (int)Math.Min(size, 1024L * 1024L);
        byte[] tail = new byte[scan];
        file.Position = size - scan;
        int read = 0;
        while (read < scan)
        {
            int count = file.Read(tail, read, scan - read);
            if (count <= 0) break;
            read += count;
        }
        // Scanning (instead of only reading the last 16 bytes) also works when an optional
        // Authenticode signature was appended after the payload trailer.
        for (int index = read - Magic.Length; index >= 8; index--)
        {
            bool matches = true;
            for (int offset = 0; offset < Magic.Length; offset++)
            {
                if (tail[index + offset] != Magic[offset]) { matches = false; break; }
            }
            if (!matches) continue;
            ulong payloadLength = BitConverter.ToUInt64(tail, index - 8);
            long candidate = size - scan + index - 8 - (long)payloadLength;
            if (payloadLength > 0 && candidate >= 0)
            {
                start = candidate;
                length = (long)payloadLength;
                return;
            }
        }
        throw new InvalidDataException("This installer file is incomplete. Download it again.");
    }

    public static Stream Open()
    {
        FileStream file = OpenFile();
        try
        {
            long start;
            long length;
            Locate(file, out start, out length);
            return new SliceStream(file, start, length);
        }
        catch
        {
            file.Dispose();
            throw;
        }
    }

    // The setup stub ends where the payload starts, so this is also the stub's size.
    public static long StartOffset()
    {
        using (FileStream file = OpenFile())
        {
            long start;
            long length;
            Locate(file, out start, out length);
            return start;
        }
    }
}

sealed class SliceStream : Stream
{
    readonly Stream inner;
    readonly long start;
    readonly long length;
    long position;

    public SliceStream(Stream inner, long start, long length)
    {
        this.inner = inner;
        this.start = start;
        this.length = length;
    }

    public override bool CanRead { get { return true; } }
    public override bool CanSeek { get { return true; } }
    public override bool CanWrite { get { return false; } }
    public override long Length { get { return length; } }
    public override long Position
    {
        get { return position; }
        set { position = value; }
    }

    public override int Read(byte[] buffer, int offset, int count)
    {
        if (position >= length) return 0;
        int wanted = (int)Math.Min(count, length - position);
        inner.Position = start + position;
        int read = inner.Read(buffer, offset, wanted);
        position += read;
        return read;
    }

    public override long Seek(long offset, SeekOrigin origin)
    {
        long next;
        if (origin == SeekOrigin.Begin) next = offset;
        else if (origin == SeekOrigin.Current) next = position + offset;
        else next = length + offset;
        position = next;
        return position;
    }

    public override void Flush() { }
    public override void SetLength(long value) { throw new NotSupportedException(); }
    public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }

    protected override void Dispose(bool disposing)
    {
        if (disposing) inner.Dispose();
        base.Dispose(disposing);
    }
}

static class Processes
{
    // The app and the background AI host (runtime\python.exe or pythonw.exe) both keep files open.
    static readonly string[] Names = { "Manim Studio", "python", "pythonw" };

    public static bool IsRunningFrom(string folder)
    {
        string root = Path.GetFullPath(folder).TrimEnd(Path.DirectorySeparatorChar)
                      + Path.DirectorySeparatorChar;
        foreach (string name in Names)
        {
            foreach (Process process in Process.GetProcessesByName(name))
            {
                try
                {
                    string path = process.MainModule.FileName;
                    if (path != null && Path.GetFullPath(path).StartsWith(root, StringComparison.OrdinalIgnoreCase))
                        return true;
                }
                catch (Exception)
                {
                    // Other users' processes cannot be inspected; they cannot belong to this install either.
                }
                finally
                {
                    process.Dispose();
                }
            }
        }
        return false;
    }
}

static class Shortcut
{
    public static void Create(string linkPath, string targetPath, string workingDirectory)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(linkPath));
            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            if (shellType == null) return;
            object shell = Activator.CreateInstance(shellType);
            try
            {
                object shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null,
                                                          shell, new object[] { linkPath });
                Type shortcutType = shortcut.GetType();
                shortcutType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut,
                                           new object[] { targetPath });
                shortcutType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut,
                                           new object[] { workingDirectory });
                shortcutType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, shortcut,
                                           new object[] { targetPath + ",0" });
                shortcutType.InvokeMember("Description", BindingFlags.SetProperty, null, shortcut,
                                           new object[] { "Manim Studio" });
                shortcutType.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
            }
            finally
            {
                try { Marshal.FinalReleaseComObject(shell); }
                catch (Exception) { }
            }
        }
        catch (Exception)
        {
            // A missing shortcut must not fail the install.
        }
    }

    public static void Delete(string linkPath)
    {
        Installer.TryDeleteFile(linkPath);
    }
}

static class UninstallEntry
{
    static string KeyPath(string name)
    {
        return @"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + name;
    }

    public static void Write(string name, string installDir)
    {
        string exe = Path.Combine(installDir, Paths.AppExe);
        string uninstall = Path.Combine(installDir, Paths.UninstallExe);
        long bytes = 0;
        try
        {
            foreach (string file in Directory.GetFiles(installDir, "*", SearchOption.AllDirectories))
                bytes += new FileInfo(file).Length;
        }
        catch (Exception) { }
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(KeyPath(name)))
        {
            if (key == null) return;
            key.SetValue("DisplayName", "Manim Studio");
            key.SetValue("DisplayVersion", Program.StudioVersion);
            key.SetValue("Publisher", "Manim Studio");
            key.SetValue("InstallLocation", installDir);
            key.SetValue("UninstallString", "\"" + uninstall + "\" /uninstall");
            key.SetValue("DisplayIcon", "\"" + exe + "\",0");
            key.SetValue("EstimatedSize", (int)Math.Min(Int32.MaxValue, bytes / 1024), RegistryValueKind.DWord);
            key.SetValue("NoModify", 1, RegistryValueKind.DWord);
            key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
        }
    }

    public static void Remove(string name)
    {
        try { Registry.CurrentUser.DeleteSubKeyTree(KeyPath(name), false); }
        catch (Exception) { }
    }
}

static class WebView2
{
    public const string DownloadUrl = "https://go.microsoft.com/fwlink/p/?LinkId=2124703";
    const string ClientId = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}";

    static bool HasRuntime(RegistryKey hive, string path)
    {
        using (RegistryKey key = hive.OpenSubKey(path))
        {
            if (key == null) return false;
            object value = key.GetValue("pv");
            string version = value == null ? null : Convert.ToString(value).Trim();
            return !String.IsNullOrEmpty(version) && version != "0.0.0.0";
        }
    }

    public static bool IsInstalled()
    {
        string clients = "Microsoft\\EdgeUpdate\\Clients\\" + ClientId;
        return HasRuntime(Registry.LocalMachine, "SOFTWARE\\WOW6432Node\\" + clients)
            || HasRuntime(Registry.LocalMachine, "SOFTWARE\\" + clients)
            || HasRuntime(Registry.CurrentUser, "Software\\" + clients);
    }

    // Returns null when the runtime is ready, else a plain explanation for the person.
    public static string Ensure(Action<string> status)
    {
        if (IsInstalled()) return null;
        string download = Path.Combine(Path.GetTempPath(),
                                       "MicrosoftEdgeWebView2Setup-" + Guid.NewGuid().ToString("N") + ".exe");
        try
        {
            status("Downloading the built-in browser engine...");
            using (WebClient client = new WebClient())
            {
                client.Headers[HttpRequestHeader.UserAgent] = "ManimStudioSetup";
                client.DownloadFile(DownloadUrl, download);
            }
            status("Checking the download...");
            if (!IsMicrosoftSigned(download))
                return BrokenDownload();
            status("Installing the built-in browser engine (this can take a minute)...");
            ProcessStartInfo info = new ProcessStartInfo(download, "/silent /install");
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            using (Process process = Process.Start(info))
            {
                if (process != null) process.WaitForExit();
            }
            if (IsInstalled()) return null;
            return BrokenDownload();
        }
        catch (Exception)
        {
            return "Manim Studio needs the built-in browser engine (WebView2) to open, and it could not be " +
                   "downloaded. The rest of the install is finished. Open Setup again when you are online " +
                   "and it will finish this step.";
        }
        finally
        {
            Installer.TryDeleteFile(download);
        }
    }

    static string BrokenDownload()
    {
        return "Manim Studio needs the built-in browser engine (WebView2) to open, and it could not be " +
               "installed. The rest of the install is finished. Open Setup again when you are online " +
               "and it will finish this step.";
    }

    static bool IsMicrosoftSigned(string path)
    {
        if (!VerifyAuthenticode(path)) return false;
        try
        {
            X509Certificate certificate = X509Certificate.CreateFromSignedFile(path);
            return certificate.Subject != null &&
                   certificate.Subject.IndexOf("Microsoft Corporation", StringComparison.OrdinalIgnoreCase) >= 0;
        }
        catch (Exception)
        {
            return false;
        }
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    sealed class WinTrustFileInfo
    {
        public uint cbStruct = (uint)Marshal.SizeOf(typeof(WinTrustFileInfo));
        public IntPtr pcwszFilePath;
        public IntPtr hFile;
        public IntPtr pgKnownSubject;
    }

    [StructLayout(LayoutKind.Sequential)]
    sealed class WinTrustData
    {
        public uint cbStruct;
        public IntPtr pPolicyCallbackData;
        public IntPtr pSIPClientData;
        public uint dwUIChoice;
        public uint fdwRevocationChecks;
        public uint dwUnionChoice;
        public IntPtr pFile;
        public uint dwStateAction;
        public IntPtr hWVTStateData;
        public IntPtr pwszURLReference;
        public uint dwProvFlags;
        public uint dwUIContext;
    }

    [DllImport("wintrust.dll", ExactSpelling = true, SetLastError = false)]
    static extern uint WinVerifyTrust(IntPtr hwnd, ref Guid action, IntPtr data);

    static bool VerifyAuthenticode(string path)
    {
        IntPtr fileInfoMemory = IntPtr.Zero;
        IntPtr dataMemory = IntPtr.Zero;
        IntPtr filePath = IntPtr.Zero;
        try
        {
            WinTrustFileInfo fileInfo = new WinTrustFileInfo();
            filePath = Marshal.StringToHGlobalUni(path);
            fileInfo.pcwszFilePath = filePath;
            fileInfoMemory = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(WinTrustFileInfo)));
            Marshal.StructureToPtr(fileInfo, fileInfoMemory, false);

            WinTrustData data = new WinTrustData();
            data.cbStruct = (uint)Marshal.SizeOf(typeof(WinTrustData));
            data.dwUIChoice = 2;              // WTD_UI_NONE
            data.fdwRevocationChecks = 0;     // WTD_REVOKE_NONE
            data.dwUnionChoice = 1;           // WTD_CHOICE_FILE
            data.pFile = fileInfoMemory;
            data.dwStateAction = 1;           // WTD_STATEACTION_VERIFY
            data.dwProvFlags = 0;             // revocation is off above; allow chain retrieval
            dataMemory = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(WinTrustData)));
            Marshal.StructureToPtr(data, dataMemory, false);

            Guid action = new Guid("00AAC56B-CD44-11d0-8CC2-00C04FC295EE");
            uint result = WinVerifyTrust(IntPtr.Zero, ref action, dataMemory);

            data = (WinTrustData)Marshal.PtrToStructure(dataMemory, typeof(WinTrustData));
            data.dwStateAction = 2;           // WTD_STATEACTION_CLOSE
            Marshal.StructureToPtr(data, dataMemory, false);
            WinVerifyTrust(IntPtr.Zero, ref action, dataMemory);
            return result == 0;
        }
        catch (Exception)
        {
            return false;
        }
        finally
        {
            if (dataMemory != IntPtr.Zero) Marshal.FreeHGlobal(dataMemory);
            if (fileInfoMemory != IntPtr.Zero) Marshal.FreeHGlobal(fileInfoMemory);
            if (filePath != IntPtr.Zero) Marshal.FreeHGlobal(filePath);
        }
    }
}

static class Uninstaller
{
    // The copy in the install folder hands off to %TEMP% so the folder can be deleted.
    public static int Launch(Options options)
    {
        try
        {
            string folder = Path.Combine(Path.GetTempPath(), "ManimStudioUninstall-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(folder);
            string copy = Path.Combine(folder, "Uninstall.exe");
            File.Copy(Application.ExecutablePath, copy, true);
            string arguments = "/uninstall /fromtemp";
            if (options.Silent) arguments += " /S";
            if (options.Directory != null) arguments += " /dir:\"" + options.Directory + "\"";
            ProcessStartInfo info = new ProcessStartInfo(copy, arguments);
            info.UseShellExecute = false;
            if (options.Silent) info.CreateNoWindow = true;
            Process.Start(info);
            return ExitCodes.Ok;
        }
        catch (Exception error)
        {
            if (!options.Silent)
                MessageBox.Show("Manim Studio could not start the uninstaller. " + error.Message,
                                "Manim Studio", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return ExitCodes.Failed;
        }
    }

    public static int Run(Options options)
    {
        int code = ExitCodes.Ok;
        try
        {
            if (!options.Silent)
            {
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new UninstallForm(options));
            }
            else if (Processes.IsRunningFrom(options.InstallDir))
            {
                code = ExitCodes.AppRunning;
            }
            else
            {
                code = Remove(options, false) ? ExitCodes.Ok : ExitCodes.Failed;
            }
        }
        finally
        {
            ScheduleSelfDelete();
        }
        return code;
    }

    public static bool Remove(Options options, bool deleteData)
    {
        try
        {
            string target = options.InstallDir;
            if (Processes.IsRunningFrom(target)) return false;
            Installer.TryDeleteDirectory(target);
            // A half-deleted folder keeps its entry, so the person can close the app and try again.
            if (Directory.Exists(target)) return false;
            if (options.Directory == null)
            {
                Shortcut.Delete(Paths.StartMenuShortcut);
                Shortcut.Delete(Paths.DesktopShortcut);
            }
            UninstallEntry.Remove(options.UninstallKeyName);
            if (deleteData) Installer.TryDeleteDirectory(Paths.DataDir);
            return true;
        }
        catch (Exception)
        {
            return false;
        }
    }

    // The temp copy cannot delete its own folder while it runs; cmd does it just after this exits.
    static void ScheduleSelfDelete()
    {
        try
        {
            string folder = Path.GetDirectoryName(Path.GetFullPath(Application.ExecutablePath));
            if (String.IsNullOrEmpty(folder)) return;
            string temp = Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar)
                          + Path.DirectorySeparatorChar;
            if (!folder.StartsWith(temp, StringComparison.OrdinalIgnoreCase)) return;
            if (!Path.GetFileName(folder).StartsWith("ManimStudioUninstall-", StringComparison.OrdinalIgnoreCase))
                return;
            ProcessStartInfo info = new ProcessStartInfo("cmd.exe",
                "/c ping -n 3 127.0.0.1 >nul & rmdir /s /q \"" + folder + "\"");
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.WindowStyle = ProcessWindowStyle.Hidden;
            Process process = Process.Start(info);
            if (process != null) process.Dispose();
        }
        catch (Exception)
        {
            // A leftover temp folder is harmless.
        }
    }
}

sealed class SetupForm : Form
{
    readonly Options options;
    readonly Button action;
    readonly ProgressBar progress;
    readonly Label status;
    readonly CheckBox desktopShortcut;
    bool installed;
    string installDir;

    public SetupForm(Options options)
    {
        this.options = options;
        Text = "Manim Studio Setup";
        ClientSize = new Size(480, 300);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.White;
        Font = new Font("Segoe UI", 9f);

        Label title = new Label();
        title.Text = "Manim Studio";
        title.Font = new Font("Segoe UI", 24f, FontStyle.Bold);
        title.AutoSize = true;
        title.Location = new Point(30, 24);

        Label intro = new Label();
        intro.Text = "Make a video without writing code.";
        intro.AutoSize = true;
        intro.Location = new Point(33, 78);

        desktopShortcut = new CheckBox();
        desktopShortcut.Text = "Put a shortcut on my desktop";
        desktopShortcut.Checked = true;
        desktopShortcut.Location = new Point(33, 110);
        desktopShortcut.AutoSize = true;

        action = new Button();
        action.Text = "Install";
        action.SetBounds(32, 142, 416, 46);
        action.BackColor = Color.Black;
        action.ForeColor = Color.White;
        action.FlatStyle = FlatStyle.Flat;
        action.FlatAppearance.BorderSize = 0;
        action.Font = new Font("Segoe UI", 11f);
        action.Cursor = Cursors.Hand;
        action.Click += OnAction;

        progress = new ProgressBar();
        progress.SetBounds(32, 200, 416, 8);
        progress.Style = ProgressBarStyle.Marquee;
        progress.MarqueeAnimationSpeed = 25;
        progress.Visible = false;

        status = new Label();
        status.SetBounds(32, 214, 416, 46);
        status.Text = "Installs just for you. No administrator password needed.";

        Label license = new Label();
        license.Text = "Includes the MIT License (LICENSE file).";
        license.ForeColor = Color.DimGray;
        license.AutoSize = true;
        license.Location = new Point(33, 268);

        Controls.Add(title);
        Controls.Add(intro);
        Controls.Add(desktopShortcut);
        Controls.Add(action);
        Controls.Add(progress);
        Controls.Add(status);
        Controls.Add(license);
    }

    void OnAction(object sender, EventArgs e)
    {
        if (installed)
        {
            OpenApp();
            Close();
            return;
        }
        while (Processes.IsRunningFrom(options.InstallDir))
        {
            DialogResult retry = MessageBox.Show(this, Messages.AppRunning,
                "Manim Studio", MessageBoxButtons.RetryCancel, MessageBoxIcon.Information);
            if (retry != DialogResult.Retry) return;
        }
        options.DesktopShortcut = desktopShortcut.Checked;
        action.Enabled = false;
        desktopShortcut.Enabled = false;
        progress.Visible = true;
        SetStatus("Getting ready...");
        Thread worker = new Thread(delegate()
        {
            InstallResult result = Installer.Install(options, SetStatus);
            ShowResult(result);
        });
        worker.IsBackground = true;
        worker.Start();
    }

    void ShowResult(InstallResult result)
    {
        if (IsDisposed || !IsHandleCreated) return;
        try
        {
            BeginInvoke((MethodInvoker)delegate
            {
                progress.Visible = false;
                action.Enabled = true;
                desktopShortcut.Enabled = true;
                if (result.Success)
                {
                    installed = true;
                    installDir = result.InstallDir;
                    action.Text = "Open Manim Studio";
                    SetStatus(result.WebView2Missing
                        ? "Manim Studio is installed, but the built-in browser engine is missing."
                        : "Manim Studio is installed.");
                    if (result.WebView2Missing)
                    {
                        MessageBox.Show(this, result.WebView2Message, "One more step",
                                        MessageBoxButtons.OK, MessageBoxIcon.Information);
                    }
                }
                else
                {
                    action.Text = "Install";
                    SetStatus(result.Message);
                    MessageBox.Show(this, result.Message, "Manim Studio",
                                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }
            });
        }
        catch (InvalidOperationException)
        {
            // The window closed while the install finished.
        }
    }

    void SetStatus(string text)
    {
        if (IsDisposed) return;
        if (InvokeRequired)
        {
            try
            {
                BeginInvoke((MethodInvoker)delegate { SetStatus(text); });
            }
            catch (InvalidOperationException) { }
            return;
        }
        status.Text = text;
    }

    void OpenApp()
    {
        try
        {
            ProcessStartInfo info = new ProcessStartInfo(Path.Combine(installDir, Paths.AppExe));
            info.WorkingDirectory = installDir;
            info.UseShellExecute = true;
            Process.Start(info);
        }
        catch (Exception error)
        {
            MessageBox.Show(this, "Manim Studio could not be opened. " + error.Message,
                            "Manim Studio", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }
}

sealed class UninstallForm : Form
{
    readonly Options options;
    readonly Button action;
    readonly Label status;
    bool removing;
    bool finished;

    public UninstallForm(Options options)
    {
        this.options = options;
        Text = "Manim Studio";
        ClientSize = new Size(480, 240);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        MinimizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.White;
        Font = new Font("Segoe UI", 9f);

        Label title = new Label();
        title.Text = "Manim Studio";
        title.Font = new Font("Segoe UI", 24f, FontStyle.Bold);
        title.AutoSize = true;
        title.Location = new Point(30, 24);

        Label intro = new Label();
        intro.Text = "This removes Manim Studio from this PC.";
        intro.AutoSize = true;
        intro.Location = new Point(33, 82);

        action = new Button();
        action.Text = "Remove Manim Studio";
        action.SetBounds(32, 120, 416, 46);
        action.BackColor = Color.Black;
        action.ForeColor = Color.White;
        action.FlatStyle = FlatStyle.Flat;
        action.FlatAppearance.BorderSize = 0;
        action.Font = new Font("Segoe UI", 11f);
        action.Cursor = Cursors.Hand;
        action.Click += OnAction;

        status = new Label();
        status.SetBounds(32, 178, 416, 46);
        status.Text = "Your videos and projects are kept unless you choose to remove them.";

        Controls.Add(title);
        Controls.Add(intro);
        Controls.Add(action);
        Controls.Add(status);
    }

    void OnAction(object sender, EventArgs e)
    {
        if (finished)
        {
            Close();
            return;
        }
        if (removing) return;
        while (Processes.IsRunningFrom(options.InstallDir))
        {
            DialogResult retry = MessageBox.Show(this, Messages.AppRunning,
                "Manim Studio", MessageBoxButtons.RetryCancel, MessageBoxIcon.Information);
            if (retry != DialogResult.Retry) return;
        }
        removing = true;
        DialogResult answer = MessageBox.Show(this,
            "Do you also want to delete your videos and projects?\n\nThey are in " + Paths.DataDir,
            "Manim Studio", MessageBoxButtons.YesNo, MessageBoxIcon.Question, MessageBoxDefaultButton.Button2);
        bool deleteData = answer == DialogResult.Yes;
        action.Enabled = false;
        SetStatus("Removing Manim Studio...");
        Thread worker = new Thread(delegate()
        {
            bool removed = Uninstaller.Remove(options, deleteData);
            Finish(removed, deleteData);
        });
        worker.IsBackground = true;
        worker.Start();
    }

    void Finish(bool removed, bool deleteData)
    {
        if (IsDisposed || !IsHandleCreated) return;
        try
        {
            BeginInvoke((MethodInvoker)delegate
            {
                removing = false;
                action.Enabled = true;
                if (removed)
                {
                    finished = true;
                    action.Text = "Close";
                    SetStatus("Manim Studio was removed. " +
                              (deleteData ? "Your videos and projects were deleted. "
                                          : "Your videos and projects were kept. ") +
                              "AI app connections were left unchanged.");
                }
                else
                {
                    action.Text = "Try again";
                    SetStatus(Processes.IsRunningFrom(options.InstallDir)
                        ? Messages.AppRunning
                        : "Manim Studio could not be removed. Close it, then try again.");
                }
            });
        }
        catch (InvalidOperationException) { }
    }

    void SetStatus(string text)
    {
        if (IsDisposed) return;
        if (InvokeRequired)
        {
            try { BeginInvoke((MethodInvoker)delegate { SetStatus(text); }); }
            catch (InvalidOperationException) { }
            return;
        }
        status.Text = text;
    }
}
