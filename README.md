# Obědy Dejvice

Scraper jídelníčků dejvických jídelen.

## Použití
Skript reaguje na `argv[0]` čili název skriptu. Ke změně názvu skriptu lze použít například symbolický link (nebo příkaz `cp`)(nebo příkaz `exec -a`)(možností je hodně).

```bash
git clone https://github.com/syyyr/obedy-dejvice
cd obedy-dejvice
ln -s $(pwd)/obedy.py ${HOME}/bin/blox
ln -s $(pwd)/obedy.py ${HOME}/bin/husa
ln -s $(pwd)/obedy.py ${HOME}/bin/country
```

## Závislosti
```
beautifulsoup4
```
