' Liga o servidor da Mesa de Agentes (se não estiver no ar) e abre o painel
Set sh = CreateObject("Wscript.Shell")
Set http = CreateObject("MSXML2.XMLHTTP")
On Error Resume Next
http.Open "GET", "http://localhost:8787/api/estado", False
http.Send
If Err.Number <> 0 Or http.Status <> 200 Then
  Err.Clear
  sh.CurrentDirectory = "C:\Users\Administrator\trading-ia\mesa"
  sh.Run """C:\Users\Administrator\AppData\Local\Programs\Python\Python312\pythonw.exe"" servidor.py", 0, False
  WScript.Sleep 2500
End If
If WScript.Arguments.Count = 0 Then sh.Run "http://localhost:8787"
