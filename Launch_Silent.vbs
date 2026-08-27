'' StreamMaster v2.0.6 — Silent Launcher
'' Starts the server without a visible console window.
'' Use Launch.bat instead if you need to see server output for debugging.

Dim shell, scriptDir

Set shell     = CreateObject("WScript.Shell")
scriptDir     = Left(WScript.ScriptFullName, _
                InStrRev(WScript.ScriptFullName, "\"))

'' Check Python is available
On Error Resume Next
shell.Run "python --version", 0, True
If Err.Number <> 0 Then
    MsgBox "Python not found." & vbCrLf & vbCrLf & _
           "Install from: https://www.python.org/downloads/" & vbCrLf & _
           "Tick 'Add Python to PATH' during installation.", _
           vbCritical, "StreamMaster"
    WScript.Quit
End If
On Error GoTo 0

'' Install packages silently if needed (runs pip, hidden)
shell.Run "python -m pip install flask flask-cors pyloudnorm soundfile scipy numpy matchering" & _
          " --quiet --disable-pip-version-check", 0, True

'' Launch the server — window style 0 = hidden
shell.Run "python """ & scriptDir & "server.py"" --no-browser", 0, False

'' Give the server a moment to start, then open the browser
WScript.Sleep 1800
shell.Run "http://localhost:5051"
