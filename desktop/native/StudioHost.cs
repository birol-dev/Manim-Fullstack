// Framework C# compiler is a build-host dependency only. No Node/Python discovery at runtime.
using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

class StudioHost
{
    [StructLayout(LayoutKind.Sequential)]
    struct BasicLimits {
        public long ProcessTime, JobTime;
        public uint Flags;
        public UIntPtr MinWorkingSet, MaxWorkingSet;
        public uint ActiveProcesses;
        public UIntPtr Affinity;
        public uint Priority, Scheduling;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct IoCounters { public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes; }
    [StructLayout(LayoutKind.Sequential)]
    struct ExtendedLimits {
        public BasicLimits Basic;
        public IoCounters Io;
        public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern IntPtr CreateJobObject(IntPtr security, string name);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool SetInformationJobObject(IntPtr job, int kind, ref ExtendedLimits limits, uint size);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")]
    static extern bool CloseHandle(IntPtr handle);

    [STAThread]
    static int Main(string[] args) {
        IntPtr job = IntPtr.Zero;
        Process child = null;
        try {
            if (args.Length != 0) throw new Exception("Use the desktop scripts for diagnostic options.");
            string root = AppDomain.CurrentDomain.BaseDirectory;
            string python = Path.Combine(root, "runtime", "pythonw.exe");
            string script = Path.Combine(root, "shell", "launcher.py");
            if (!File.Exists(python) || !File.Exists(script)) throw new Exception("Studio's bundled runtime is missing. Extract the entire portable folder.");
            job = CreateJobObject(IntPtr.Zero, null);
            if (job == IntPtr.Zero) throw new System.ComponentModel.Win32Exception();
            var limits = new ExtendedLimits();
            // KILL_ON_JOB_CLOSE plus BREAKAWAY_OK: an update installer may leave the job.
            limits.Basic.Flags = 0x2000 | 0x0800; // handle never inherited
            if (!SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf(limits))) throw new System.ComponentModel.Win32Exception();
            var info = new ProcessStartInfo(python, "-B \"" + script + "\" --app-root \"" + root.TrimEnd('\\') + "\"");
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.RedirectStandardInput = true;
            info.EnvironmentVariables["STUDIO_HOST_GATE"] = "1";
            child = Process.Start(info);
            if (!AssignProcessToJobObject(job, child.Handle)) throw new System.ComponentModel.Win32Exception();
            child.StandardInput.WriteLine("start");
            child.StandardInput.Flush();
            child.WaitForExit();
            return child.ExitCode;
        } catch (Exception error) {
            MessageBox.Show(error.Message, "Manim Studio", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        } finally {
            if (job != IntPtr.Zero) CloseHandle(job);
            if (child != null) {
                try { if (!child.HasExited) child.Kill(); } catch { }
                child.Dispose();
            }
        }
    }
}
