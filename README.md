# Perearsti teatmik

Kiirotsing perearsti töös vajalike koodide, piirhindade, fondide, abivahendite ja juhi tervisenõuete kohta. Töötab brauseris ja pärast esimest avamist ka võrguta.

**Rakendus:** https://immot1-max.github.io/perearsti-teatmik/

## Mis seal on

| Allikas | Mida sealt võetakse |
|---|---|
| Tervisekassa tervishoiuteenuste loetelu | Kõik koodid ja piirhinnad, rakendamise tingimused, perearstiabi peatükk |
| Tasu maksmise kohustuse ülevõtmise kord ja metoodika | § 6 fondid (uuringufond kuni 37%, tegevusfond raviarvega lisaks, teraapiafond kuni 13%), perearstiabi peatükk (§ 4–8¹) |
| Abivahendite loetelu, tõendi ja kaardi andmed | Määruse tekst ja lisa (abivahendite loetelu) |
| Mootorsõidukijuhi tervisekontroll ja tervisenõuded | Kogu määruse tekst |
| Metoodika § 8 ja Tervisekassa kvaliteedisüsteemi leht | Kvaliteedisüsteemi kriteeriumid, koodid, punktid ja lisapädevuste koodiloetelud; Tervisekassa uusimad juhendid |
| Tervisekassa meditsiiniseadmete loetelu (tervise- ja tööministri määrus nr 86) | 64 rühma: hüvitamise tingimused (§ 4–63⁴), alarühmad ja tooted koos piirhindadega; rühmakoodid 9MS failist `build/ms_ryhmakoodid.json` |
| SYNLABi hinnakiri (tervishoiuteenuse pakkujale) | Analüüsi nimi, lühend, Tervisekassa kood ja hind; analüüsilt koodini ja koodilt analüüsideni |
| Terviseportaal: vähi sõeluuringud | Rinna-, emakakaela- ja soolevähi sõeluuringu vanus, intervall ja jooksva aasta sünniaastad; koodid ja raviarve info failist `build/soeluuringud.json` |
| Tervisekassa: kopsuvähi sõeluuring | Tegevusjuhendi link ja lehe uuendamise kuupäev; sihtrühm ja kodeerimine failist `build/soeluuringud.json` |
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

## Kvaliteedisüsteem

Kriteeriumid, koodid, punktid ja koefitsiendid loetakse automaatselt metoodika § 8 tabelitest, nii et need uuenevad koos määrusega. Tervisekassa juhendites olevad lisaselgitused (vanused, kodeerimisreeglid, lisapädevuse lävendid) on failis `build/ks_notes.json`. Kontroll vaatab iga kuu ka Tervisekassa kvaliteedisüsteemi lehte. Kui seal ilmuvad uue aasta juhendid, märgib ta selle teavitusse ja `ks_notes.json` tuleb üle vaadata.

## Sõeluuringud

Igal kontrollil loetakse terviseportaali lehelt https://www.terviseportaal.ee/haiguste-ennetus/soeluuringud iga programmi vanusevahemik, intervall ja kutsutavad sünniaastad. Skript kontrollib, et sünniaastatest arvutatud vanused klapivad lehel nimetatud vanusega, et sünniaastate vahe vastab intervallile ja et alamlehe sünniaastad ühtivad koondlehega. Kui midagi ei klapi või lehte ei saa, jääb alles eelmine seis ja teavitusse tuleb märkus. Uue aasta sünniaastad jõuavad rakendusse järgmisel kuukontrollil pärast seda, kui terviseportaal need avaldab.

Rakenduses näitab sünniaasta otsing (nt „1966“), millise sõeluuringu sihtrühma inimene sel aastal kuulub.

## Sünonüümid

`build/synonyms.json` seob argisõnad ametlike nimetustega, nt „holter“ → 6371 „EKG monitooring 24 tundi“. Faili saab GitHubis otse muuta; pärast salvestamist ehitatakse andmed automaatselt uuesti.

## Ainult perearstiabi

Vaikimisi näidatakse teenustest ainult neid, mis kuuluvad perearsti fondidesse, kvaliteedisüsteemi või perearstiabi peatükki (424 koodi 15.10.2026 seisuga). Linnukese eemaldamisel on nähtavad kõik koodid, ka operatsioonid ja haiglateenused. Täpse koodi otsing näitab koodi alati.

## Autor

Idee ja sisu: Tommi Ründal, perearst (Medicum Perearstikeskus). Rakendus on ehitatud Claude'i (Anthropic) abil. Isiklik projekt, mitte Tervisekassa ega Medicumi ametlik tööriist.

## Vastutus

Õiguslikult kehtib alati Riigi Teatajas avaldatud tekst. Rakendus on abivahend kiireks otsinguks ja viitab igal kirjel algallikale.
