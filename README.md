# Honka 3 – kausiyhteenveto

Automaattisesti päivittyvä sivu Honka 3 -joukkueen (Miesten III divisioona,
Eteläinen alue) kauden 2026–2027 tilastoista: pelatut ottelut, koti/vieras-jako,
kunkin ottelun kolme parasta pistemiestä, pelaajakohtaiset tilastot
(piste-keskiarvo, voitto-%) ja seuraavat ottelut.

**Sivu:** https://njuntunen-junde.github.io/honka3-stats/

## Miten se toimii

- `scrape.py` hakee tiedot [tulospalvelu.basket.fi](https://tulospalvelu.basket.fi/team/815/info?title=Honka+3&club_id=1515&season=2026-2027):sta
  Playwrightilla (sivu on React-sovellus, joten pelkkä HTTP-pyyntö ei riitä) ja
  tallentaa kaiken `data.json`-tiedostoon.
- `render.py` lukee `data.json`:n ja kirjoittaa `index.html`:n.
- GitHub Actions -workflow (`.github/workflows/update.yml`) ajaa molemmat
  joka ilta klo 21:30 UTC (23:30/00:30 Suomen aikaa) ja committaa muutokset,
  jos jotain on muuttunut — eli käytännössä aina kun Honka 3 on pelannut
  ottelun samana iltana.
- Workflow voi ajaa myös manuaalisesti: **Actions → Päivitä Honka 3
  -yhteenveto → Run workflow**.

## Datalähde ja rajoitukset

Sivu lukee vain tulospalvelu.basket.fi:n julkisia, selaimessa renderöityjä
sivuja (sallittu heidän robots.txt:nsä mukaan — vain `/person/` on kielletty).
Se ei kutsu suoraan taustalla olevaa `koripallo-api.torneopal.net`-rajapintaa,
koska se host kieltää botit robots.txt:ssään.

Joidenkin otteluiden kokoonpanosivulta ei ole saatavilla pelaajakohtaisia
pisteitä (esim. jos ottelupöytäkirjaa ei ole täytetty) — näissä tapauksissa
sivu kertoo sen suoraan eikä arvaa lukuja.
