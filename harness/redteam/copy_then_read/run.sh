set -e
cp /opt/venv/lib/python3.12/site-packages/skimage/data/coffee.png /tmp/a.dat
/opt/venv/bin/python src/draw.py
