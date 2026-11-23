# Flat Finder integration

Use one map for property markers and Localytics neighbourhood scores. Expand **Neighbourhood filters · Delhi** beside the property filters to adjust all ten Localytics factors. The Delhi scoring grid and Gurugram listings have separate coverage.

From your Localytics checkout, run:

```sh
git clone https://github.com/kairothq/flat-finder.git ../flat-finder-localytics
git -C ../flat-finder-localytics checkout --detach f7a46122979c23176ce0f57c0394c2444d5e82c8
git -C ../flat-finder-localytics apply --unidiff-zero "$PWD/integrations/flat-finder/flat-finder.patch"
cp -R integrations/flat-finder/files/. ../flat-finder-localytics/
python ../flat-finder-localytics/integration/localytics_api.py .
```

Use your Localytics Python environment and a populated `data/areas.sqlite`. Keep that terminal running. In another terminal, from the Localytics checkout:

```sh
cd ../flat-finder-localytics/web
npm ci
npm run dev -- --host 127.0.0.1 --strictPort
```

Open [the local app](http://127.0.0.1:5173/?nointro). The Python service uses cached air-quality observations. PM2.5 only contributes to rankings when an observation meets the existing freshness and distance requirements.
