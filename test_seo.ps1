$urls = @(
    @{ url = "https://lotoia.fr/";                  expect = 200; label = "Homepage" },
    @{ url = "https://lotoia.fr/robots.txt";        expect = 200; label = "robots.txt" },
    @{ url = "https://lotoia.fr/sitemap.xml";       expect = 200; label = "sitemap.xml" },
    @{ url = "https://lotoia.fr/accueil";           expect = 200; label = "/accueil" },
    @{ url = "https://lotoia.fr/loto";              expect = 200; label = "/loto" },
    @{ url = "https://lotoia.fr/simulateur";        expect = 200; label = "/simulateur" },
    @{ url = "https://lotoia.fr/statistiques";      expect = 200; label = "/statistiques" },
    @{ url = "https://lotoia.fr/faq";               expect = 200; label = "/faq" },
    @{ url = "https://lotoia.fr/news";              expect = 200; label = "/news" },
    @{ url = "https://lotoia.fr/ui/launcher.html";  expect = 301; label = "/ui/launcher.html" },
    @{ url = "https://lotoia.fr/ui/loto.html";      expect = 301; label = "/ui/loto.html" },
    @{ url = "https://lotoia.fr/ui/simulateur.html"; expect = 301; label = "/ui/simulateur.html" },
    @{ url = "https://www.lotoia.fr/";              expect = 301; label = "www redirect" },
    @{ url = "http://lotoia.fr/";                   expect = 301; label = "http redirect" }
)

Write-Output ""
Write-Output ("| {0,-25} | {1,-6} | {2,-30} | {3,-10} | {4}" -f "URL", "Status", "Content-Type", "Location", "Result")
Write-Output ("| {0,-25} | {1,-6} | {2,-30} | {3,-10} | {4}" -f ("-"*25), ("-"*6), ("-"*30), ("-"*10), "------")

foreach ($item in $urls) {
    try {
        $r = Invoke-WebRequest -Uri $item.url -Method HEAD -MaximumRedirection 0 -ErrorAction Stop -UseBasicParsing
        $status = $r.StatusCode
        $ct = if ($r.Headers["Content-Type"]) { $r.Headers["Content-Type"] } else { "-" }
        $loc = if ($r.Headers["Location"]) { $r.Headers["Location"] } else { "-" }
    } catch {
        $resp = $_.Exception.Response
        if ($resp) {
            $status = [int]$resp.StatusCode
            $ct = "-"
            $loc = "-"
            try { $ct = $resp.Headers.GetValues("Content-Type") -join ", " } catch {}
            try { $loc = $resp.Headers.GetValues("Location") -join ", " } catch {}
        } else {
            $status = "ERR"
            $ct = $_.Exception.Message.Substring(0, [Math]::Min(30, $_.Exception.Message.Length))
            $loc = "-"
        }
    }

    if ($item.expect -eq 200) {
        $ok = if ($status -eq 200) { "OK" } else { "KO" }
    } else {
        $ok = if ($status -eq 301 -or $status -eq 302 -or $status -eq 307 -or $status -eq 308) { "OK" } else { "KO" }
    }

    Write-Output ("| {0,-25} | {1,-6} | {2,-30} | {3,-10} | {4}" -f $item.label, $status, $ct, $loc, $ok)
}

Write-Output ""
Write-Output "--- robots.txt content ---"
(Invoke-WebRequest -Uri "https://lotoia.fr/robots.txt" -UseBasicParsing).Content
Write-Output ""
Write-Output "--- sitemap.xml content ---"
(Invoke-WebRequest -Uri "https://lotoia.fr/sitemap.xml" -UseBasicParsing).Content
