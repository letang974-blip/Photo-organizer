from setuptools import setup

APP = ['Photo organizer.py']  # Your entry point script
OPTIONS = {
    'argv_emulation': True,
    'iconfile': 'tri.icns',  # Custom icon
    'plist': {
        'CFBundleName': 'Photo Organizer',
        'CFBundleDisplayName': 'Photo Organizer',
        'CFBundleIdentifier': 'com.yourname.photoorganizer',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
    }
}

setup(
    app=APP,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
