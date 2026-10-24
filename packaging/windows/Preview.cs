using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Windows.Forms;

internal static class Preview {
    [STAThread] private static void Main(string[] args) {
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        using(var form=new SetupForm(new InstallOptions())) {
            form.ShowInTaskbar=false;form.StartPosition=FormStartPosition.Manual;form.Location=new Point(-20000,-20000);form.Opacity=0;
            form.Show();Application.DoEvents();form.PerformLayout();
            using(var image=new Bitmap(form.Width,form.Height)) {form.DrawToBitmap(image,new Rectangle(0,0,form.Width,form.Height));image.Save(args[0],ImageFormat.Png);}
        }
    }
}
