# Perearsti teatmik

Kiirotsing perearsti töös vajalike koodide, piirhindade, fondide, sõeluuringute, haigus- ja hoolduslehtede, tervisetõendite, vaktsineerimise, retseptide, e-konsultatsiooni, patsiendi hüvitiste, abivahendite ja juhi tervisenõuete kohta, lisaks koolivaheajad, patsiendi küsimustike ja päevikute otselingid, koloskoopia ja gastroskoopia ettevalmistusjuhendid ning kõigi kinnitatud ravijuhendite otselingid koos valitud lisadega. Näitab ka, mis allikates viimasel ajal muutus või peagi muutub. Töötab brauseris ja pärast esimest avamist ka võrguta.

Avalehe kohal on vahelehed: „Avaleht“ (kõik), „Rahastus“ (fondid, pearaha ja lisatasud, kvaliteedisüsteem, sõeluuringud, loetelu ja metoodika muudatused), „Seadused ja nõuded“ (igapäevatöö reeglid, abivahendid, meditsiiniseadmed, teiste aktide muudatused), „Küsimustikud ja infolehed“ (teemakaardirühmad „Küsimustikud ja päevikud“ ja „Infolehed patsiendile“, kasulikud lingid) ning „Ravijuhendid“ (lisa pildina või Medicumi tabelitega juhendid, kõik ravijuhendid ja käsitlusjuhendid nimekirjana, patsiendijuhendid ja antimikroobse ravi rakendus). Vaheleht määrab, mida näidatakse ilma otsinguta ja millised kategooriakiibid on reas; otsing otsib alati kõigist andmetest. Vahelehe saab avada aadressiga `?tab=rahastus`, `?tab=noud`, `?tab=kys` või `?tab=rj`. Kitsal ekraanil (alla 390 px) keritakse vahelehtede rida külgsuunas ja valitud vaheleht keritakse nähtavale. Vahelehtede seadistus on `app.js` konstantides `TABS`, `TAB_CHIPS`, `KYS_GROUPS` ja `RAHASTUS_SRC`.

**Rakendus:** https://immot1-max.github.io/perearsti-teatmik/

## Mis seal on

| Allikas | Mida sealt võetakse |
|---|---|
| Tervisekassa tervishoiuteenuste loetelu | Kõik koodid ja piirhinnad, rakendamise tingimused, perearstiabi peatükk |
| Tasu maksmise kohustuse ülevõtmise kord ja metoodika | § 6 fondid (uuringufond kuni 37%, tegevusfond raviarvega lisaks, teraapiafond kuni 13%, mida tasutakse ainult siis, kui teenust osutab perearsti enda äriühing või FIE, § 6 lg 9), perearstiabi peatükk (§ 4–8¹); lisa „Teenuste standardkulu komponendid“ (iga koodi ressursid, sh arsti minutid) ja e-konsultatsiooni saatekirja nõuete lisad erialade kaupa |
| Abivahendite loetelu, tõendi ja kaardi andmed | Määruse tekst ja lisa (abivahendite loetelu) |
| Mootorsõidukijuhi tervisekontroll ja tervisenõuded | Kogu määruse tekst |
| Metoodika § 8 ja Tervisekassa kvaliteedisüsteemi leht | Kvaliteedisüsteemi kriteeriumid, koodid, punktid ja lisapädevuste koodiloetelud; Tervisekassa uusimad juhendid |
| Tervisekassa meditsiiniseadmete loetelu (tervise- ja tööministri määrus nr 86) | 64 rühma: hüvitamise tingimused (§ 4–63⁴), alarühmad ja tooted koos piirhindadega; rühmakoodid 9MS failist `build/ms_ryhmakoodid.json` |
| SYNLABi hinnakiri (tervishoiuteenuse pakkujale) | Analüüsi nimi, lühend, Tervisekassa kood ja hind; analüüsilt koodini ja koodilt analüüsideni |
| Terviseportaal: vähi sõeluuringud | Rinna-, emakakaela- ja soolevähi sõeluuringu vanus, intervall ja jooksva aasta sünniaastad; koodid ja raviarve info failist `build/soeluuringud.json` |
| Tervisekassa: kopsuvähi sõeluuring | Tegevusjuhendi link ja lehe uuendamise kuupäev; sihtrühm ja kodeerimine failist `build/soeluuringud.json` |
| Riigi Teataja: töövõimetus | Ravikindlustuse seadus § 50–62, TTOS § 12², 12⁴, 12⁵, töövõimetuslehe määrus |
| Riigi Teataja: tervisetõendid | Relvaseadus § 35, 35¹ ja relvaloa tervisekontrolli määrus, abipolitseiniku seadus § 6 ja määrus, Kaitseliidu seadus § 28, kaitseväe tervisehindamise määrus, NETS § 13 |
| Riigi Teataja: nakkushaigused ja vaktsineerimine | Nakkushaiguste määrus, TIS-i põhimäärus § 5, NETS § 8, 10, 21, immuniseerimiskava koos lisadega, immuniseerimise korraldus |
| Riigi Teataja: töökorraldus ja nimistu | Perearstiabi töökorralduse määrus (nr 14), nimistu määrus (nr 47), TTKS § 4³, 7, 8, 8¹, 35 |
| Riigi Teataja: tervishoiuteenuse osutamisel osalejad | Määrus „Tervishoiuteenuse osutamisel osalevad isikud ja tervise infosüsteemile juurdepääsu ulatus“ § 2, 3 (arst-resident, abiarst, juurdepääs TIS-ile) |
| Riigi Teataja: ravimid ja hüvitised | Ravimite väljakirjutamise määrus § 2 (pereõe retseptiõigus, kogused, korduvretsept, bensodiasepiinid), RaKS § 29, 33, 33¹, 41, 42, 44, 49¹, 69, 70, 72; tervishoiuteenuste loetelu § 77 ja § 80 (hambaravi- ja proteesihüvitis) |
| Riigi Teataja: meremehe tervisenõuded | Meremehe ja mereõppeasutusse õppima asuja tervisenõuete määrus § 5, 6, 7, 12, 13 |
| Riigi Teataja: koolivaheajad | Haridus- ja teadusministri määrused nr 45 (2026/2027) ja nr 36 (2027/2028–2029/2030, jõustub 01.09.2027); tabel teemakaardil „Koolivaheajad“, ülevaatuse meeldetuletus 01.09.2027 |
| Küsimustikud, päevikud ja patsiendi infolehed | Otselingid ja kasutusreeglid: EEK-2 ja Peaasi enesetundetest, SNAP-IV-26, unepäevik ja uneküsimustikud (Epworth, STOP-BANG, ISI, PSQI), peavalupäevik ja testid, urineerimispäevikud ja IPSS, AUDIT ja nikotiinisõltuvuse test; rühmas „Infolehed patsiendile“ koloskoopia ja gastroskoopia ettevalmistusjuhendid haiglate kaupa (Kliinikum, ITK, Medicum, Tervisekassa, Regionaalhaigla, LTKH) koos dieedi erinevustega; eesti, vene ja inglise keeles, kui olemas. Linkide kättesaadavust kontrollitakse igal kuul |
| Tervisekassa: hüvitiste võrdlustabel | Haigus- ja hoolduslehe põhjused, kes maksab, määr, kestus ja päevane ülempiir (loetakse igal kontrollil) |
| Toru (Tervisekassa) | Hinna kehtivuse algus, eelmine hind, koodid, mida loetelu tabelites ei ole |
| Sotsiaalkindlustusamet | Lingid juhenditele ja vormidele |
| ravijuhend.ee | Kõik RJNK kinnitatud ravijuhendid ja käsitlusjuhendid: kood, kinnitamise ja avaldamise kuupäev, erialad, võtmesõnad (otsingus sünonüümid), lisade otselingid, kogu juhendi PDF ja patsiendijuhend; valitud lisad pildina |

## Mis muutus

Vaade „Mis muutus (seadused ja määrused)“ (avalehe lõpus ja kategooriana) võrdleb iga jälgitava seaduse ja määruse viimase 12 kuu jooksul jõustunud ja Riigi Teatajas juba avaldatud tulevasi redaktsioone eelmisega (`build/muutused.py`):

- tervishoiuteenuste loetelu: uued ja kadunud koodid, hinna- ja nimetuse muutused (linnuke „Ainult perearstiabi“ kehtib ka siin);
- metoodika: fondidesse lisandunud ja neist välja jäänud koodid ning muutunud sätted (§ 8 koos tabelitega);
- abivahendite ja meditsiiniseadmete loetelu: muudetud, uued ja kadunud read;
- teised aktid: jälgitavate paragrahvide muutunud lõiked, varasem ja uus sõnastus koos esile tõstetud muutustega;
- kõigil aktidel: uued, muudetud ja kehtetuks tunnistatud lisad.

Tervishoiuteenuste loetelu antakse aasta jooksul välja uue aktina; eelmise akti grupp on failis `build/sources.json` väljal `eelmised` ja skript lisab selle automaatselt, kui akt asendatakse.

## Mis on hinnas

Teenuse koodi juures on plokk „Mis on hinnas“: metoodika lisa „Teenuste standardkulu komponendid“ (2026. aastal lisa 3) järgi iga ressurss (personal minutites, ruumid, seadmed, materjalid, muud kulud), selle keskmine maht ja ühiku maksumus. Ülal on kokku arsti aeg minutites. Komponentide summa võib piirhinnast veidi erineda. Lisa PDF (üle 300 lehekülje) parsitakse `build/met_lisad.py` abil ja tulemus hoitakse vahemälus redaktsiooni ID järgi.

## Tagasiside

Otsingutulemuste all on nupp „Ei leidnud?“, mis avab selle repo GitHubi *issue* vormi otsisõnaga. Vorm vajab GitHubi kontot. Aadressi saab muuta `app.js` konstandis `FEEDBACK_URL` (nt Google'i vormi vastu).

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

## Igapäevatöö reeglid (teemakaardid)

Haigus- ja hooldusleht, töövõimetuslehe vormistamine, P21, tervisetõendid (relvaluba, meremees, abipolitseinik, Kaitseliit, kaitsevägi, toidukäitleja jt nakkushaiguste tõend), nakkushaiguse teatis, vaktsineerimine, töökorraldus, nimistu, PADI, perearsti, erialata arsti ja pereõe õigused, retseptid ja ravimisoodustus, e-konsultatsioon, patsiendi hüvitised ja omaosalus, tervishoiutöötajate töötasu alammäärad (kollektiivleping 2025–2026) ning peremeditsiini residentuur, 6. kursuse kliiniline praktika ja abiarst (kava, palk, tööaeg, puhkus ja lisapuhkus, juhendamine, praktikapäevik). Kaardid võivad viidata seotud kaartidele (väli `seotud`). Kokkuvõtted on failis `build/teemad.json`; need põhinevad Tommi allikaregistril (15.10.2026) ja on üle kontrollitud aktide kehtivast tekstist.

Avalehel on kaardid kuues värviga eristatud rühmas: töövõimetus; tervisetõendid (esimesena juhi tervisetõend eraldi 1. ja 2. grupi kohta, siis relvaluba, toidukäitleja jt, Kaitseliit, abipolitseinik, kaitsevägi, meremees; sama värv kui juhi tervisenõuetel); nakkushaigused ja vaktsineerimine; ravimid, suunamine ja hüvitised; töökorraldus ja nimistu; residendid, praktikandid ja abiarstid (allikad: TÜ residentuuri eeskiri, programm ja KKK, kliinilise praktika päevik, kollektiivleping, määrus nr 71 muudatus RT I, 25.03.2026, 1, TTKS § 4³ ja määrus „Tervishoiuteenuse osutamisel osalevad isikud ja tervise infosüsteemile juurdepääsu ulatus“, EAÜS ja Eesti Arst). Rühmade ja kaartide järjekord tuleb failist `build/teemad.json`.

Iga punkti juures on viide sättele (avaneb rakenduses) või allikale. Automaatne kontroll teeb igal kuul kolm asja:

1. Iga punkti `kontroll`-lõik peab kehtivas sättes alles olema. Kui akt muutub ja lõik kaob, märgitakse punkt rakenduses „allika tekst muutunud“ ja teavitusse tuleb märkus.
2. Tervisekassa hüvitiste võrdlustabel, päevane ülempiir, immuniseerimiskava lisad ja töövõimetuslehe põhjuse koodid loetakse otse allikast.
3. Tervisekassa ja Terviseameti lehtede „Viimati uuendatud“ kuupäev ja PDF-ide sisu jälgitakse; muutusest tuleb teavitus koos soovitusega teemakaart üle vaadata. Kaardil võib olla ka ülevaatuse kuupäev (väli `ule`, nt töötasu alammäärade kaardil 01.01.2027, kui kollektiivleping lõpeb); sellest alates tuleb teavitusse meeldetuletus.

Allikate omavahelised vastuolud on kaardil „Erinevused allikates“ all (nt õe õigused töövõimetuslehel, perearsti vahetuse kuupäev, P21 juhendi 15./16. päev, Tervisekassa aegunud patsiendilehed).

## Ravijuhendid

Skript `build/ravijuhendid.py` loeb igal kontrollil ravijuhend.ee loendist (sama JSON, mida kasutab leht https://ravijuhend.ee/tervishoiuvarav/juhendid) kõik RJNK kinnitatud ravijuhendid ja käsitlusjuhendid ning iga juhendi lehelt koodi, kinnitamise ja avaldamise kuupäeva, erialad, võtmesõnad, lisad, kogu juhendi PDF-i ja patsiendijuhendi lingi. Patsiendijuhendid on eraldi kirjena ainult üldlingina.

Failis `build/ravijuhendid.json` on:

- `eelvaade`: millised lisad näidatakse juhendi kirjes kohe pildina (lisa number ja kontrollsõna pealkirjas). Pilt tehakse lisa PDF-ist; kui lisal PDF-i pole, otsitakse lisa leheküljed kogu juhendi PDF-ist ja viimase võimalusena võetakse juhendi lehe pildid. Pildid on kaustas `lisad/` ja tehakse uuesti ainult siis, kui allika räsi muutus. Kui lisade numeratsioon muutub, otsitakse sama kontrollsõnaga lisa ja aruandesse tuleb märkus.
- `syn`, `sn`, `ks`, `seotud`, `lingid`: lisasünonüümid, avalehe lühinimi, seos kvaliteedisüsteemi jaotisega, seotud teemakaardid ja lisalingid (nt TÜ Kliinikumi antimikroobse ravi rakendus infektsioonide juhendites).
- `kasitsi`: käsitsi lisatud sisu, mida automaatkontroll ei uuenda (Medicumi majasisesed vererõhu ja SCORE2 riskitabelid kõrgvererõhktõve juhendi juures). Kui juhendist ilmub uus versioon, tuleb aruandesse meeldetuletus see üle vaadata.

Uued ja kadunud juhendid, uued versioonid (kood või kinnitamise kuupäev muutus), muutunud lisad ja eelvaated on aruandes jaotises „Ravijuhendid“. Kui ravijuhend.ee pole kättesaadav, jääb alles eelmine seis.

## Sünonüümid

`build/synonyms.json` seob argisõnad ametlike nimetustega, nt „holter“ → 6371 „EKG monitooring 24 tundi“. Faili saab GitHubis otse muuta; pärast salvestamist ehitatakse andmed automaatselt uuesti.

## Ainult perearstiabi

Vaikimisi näidatakse teenustest ainult neid, mis kuuluvad perearsti fondidesse, kvaliteedisüsteemi või perearstiabi peatükki (424 koodi 15.10.2026 seisuga). Linnukese eemaldamisel on nähtavad kõik koodid, ka operatsioonid ja haiglateenused. Täpse koodi otsing näitab koodi alati.

## Autor

Idee ja sisu: Tommi Ründal, perearst (Medicum Perearstikeskus). Rakendus on ehitatud Claude'i (Anthropic) abil. Isiklik projekt, mitte Tervisekassa ega Medicumi ametlik tööriist.

## Vastutus

Õiguslikult kehtib alati Riigi Teatajas avaldatud tekst. Rakendus on abivahend kiireks otsinguks ja viitab igal kirjel algallikale.
