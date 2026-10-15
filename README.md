# Perearsti teatmik

Kiirotsing perearsti töös vajalike koodide, piirhindade, fondide, abivahendite ja juhi tervisenõuete kohta. Töötab brauseris ja pärast esimest avamist ka võrguta.

**Rakendus:** https://immot1-max.github.io/perearsti-teatmik/

## Mis seal on

| Allikas | Mida sealt võetakse |
|---|---|
| Tervisekassa tervishoiuteenuste loetelu | Kõik koodid ja piirhinnad, rakendamise tingimused, perearstiabi peatükk |
| Tasu maksmise kohustuse ülevõtmise kord ja metoodika | § 6 fondid (kuni 37%, kuni 13%, raviarvega lisaks), perearstiabi peatükk (§ 4–8¹) |
| Abivahendite loetelu, tõendi ja kaardi andmed | Määruse tekst ja lisa (abivahendite loetelu) |
| Mootorsõidukijuhi tervisekontroll ja tervisenõuded | Kogu määruse tekst |
| Toru (Tervisekassa) | Hinna kehtivuse algus, eelmine hind, koodid, mida loetelu tabelites ei ole |
| Sotsiaalkindlustusamet | Lingid juhenditele ja vormidele |

## Kuidas andmed uuenevad

GitHub Actions käivitab iga kuu 3. kuupäeval kontrolli (`.github/workflows/uuenda.yml`). Skript `build/build.py` küsib Riigi Teataja avalikust liidesest iga akti kehtiva redaktsiooni. Kui midagi on muutunud, ehitab ta `data/data.json` uuesti, salvestab selle ja avab selles repos *issue*, kus on muudatuste kokkuvõte (GitHub saadab selle kohta e-kirja). Kontrolli saab käivitada ka käsitsi: Actions → Andmete kontroll → Run workflow.

Tervishoiuteenuste loetelu antakse aasta jooksul välja uue aktina (2026. aastal 01.01, 01.04 ja 01.07). Skript tuvastab, kui akt on kehtetuks tunnistatud, ja liigub asendava akti juurde.

Rakendus kontrollib iga avamise ajal, kas uuem andmeversioon on olemas, ja laeb selle alla. Võrguta kasutatakse viimati laaditud andmeid.

## Toru uuendamine

Toru toorfaili repos ei hoita, sest repo on avalik. Repos on ainult sellest tehtud väljavõte `build/toru/toru_valjavote.json` (kood, nimetus, hind, kehtivus ja liik kolme viimase perioodi kohta). Uue Toru faili saab lisada kahel viisil:

1. Anna fail Claude'ile, mis teeb uue väljavõtte.
2. Kui Toru fail on avalik, laadi see GitHubis kausta `build/toru/` (Add file → Upload files). Kui kaustas on mitu faili, valitakse see, mille hinnaread on kõige uuemad.

## Sünonüümid

`build/synonyms.json` seob argisõnad ametlike nimetustega, nt „holter“ → 6371 „EKG monitooring 24 tundi“. Faili saab GitHubis otse muuta; pärast salvestamist ehitatakse andmed automaatselt uuesti.

## Vastutus

Õiguslikult kehtib alati Riigi Teatajas avaldatud tekst. Rakendus on abivahend kiireks otsinguks ja viitab igal kirjel algallikale.
