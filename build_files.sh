# !/bin/bash
echo "Building the project..."
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --noinput --clear
echo "Build completed"