# Obědy

Scraper jídelníčků jídelen.

## Použití
Skript reaguje na `argv[0]` čili název skriptu. Ke změně názvu skriptu lze použít například symbolický link (nebo příkaz `cp`)(nebo příkaz `exec -a`)(možností je hodně).

```bash
git clone https://github.com/syyyr/obedy
cd obedy
ln -s $(pwd)/obedy-dejvice.py ${HOME}/bin/blox
ln -s $(pwd)/obedy-dejvice.py ${HOME}/bin/husa
ln -s $(pwd)/obedy-dejvice.py ${HOME}/bin/country
```

## Závislosti
```
beautifulsoup4
```
