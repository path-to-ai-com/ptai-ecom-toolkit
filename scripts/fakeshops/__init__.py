"""Fake-Shops einer Marke finden, prüfen und melden.

Ebene 1 des Fake-Shop-Checks: neue Domains, deren Name mit der Marke beginnt,
aus den öffentlichen Zertifikatslogs (crt.sh), danach Abruf, DNS, Hoster und
Urteil je Domain. Getestet am 28.10.2026 mit sieben Marken; die Suche über
Google und die Meta-Werbebibliothek fand dort keinen einzigen Fake, die
Zertifikatslogs fanden alle.
"""
