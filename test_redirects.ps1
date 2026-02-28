$urls = @(
    "https://lotoia.fr/ui/launcher.html",
    "https://lotoia.fr/ui/loto.html",
    "https://lotoia.fr/ui/simulateur.html",
    "https://www.lotoia.fr/",
    "http://lotoia.fr/"
)

foreach ($url in $urls) {
    try {
        # Use HttpWebRequest to avoid auto-redirect
        $req = [System.Net.HttpWebRequest]::Create($url)
        $req.Method = "GET"
        $req.AllowAutoRedirect = $false
        $req.Timeout = 10000
        $resp = $req.GetResponse()
        $status = [int]$resp.StatusCode
        $loc = $resp.Headers["Location"]
        $ct = $resp.ContentType
        $resp.Close()
        Write-Output "$url => $status | Location: $loc | CT: $ct"
    } catch {
        $resp = $_.Exception.InnerException
        if ($resp -and $resp.Response) {
            $r = $resp.Response
            $status = [int]$r.StatusCode
            $loc = $r.Headers["Location"]
            $ct = $r.ContentType
            Write-Output "$url => $status | Location: $loc | CT: $ct"
            $r.Close()
        } else {
            Write-Output "$url => ERROR: $($_.Exception.Message)"
        }
    }
}
