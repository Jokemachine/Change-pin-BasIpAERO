' Скрипт для скрытого запуска ротации кодов в Планировщике Windows (без черного окна)
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)

pythonExe = currentDir & "\.venv\Scripts\python.exe"
If Not fso.FileExists(pythonExe) Then
    pythonExe = "python.exe"
End If

cmd = """" & pythonExe & """ """ & currentDir & "\main.py"" run"
WshShell.Run cmd, 0, True
