from setuptools import setup, find_packages

setup(
    name="netwatcher",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "click",
        "rumps",
        "pyobjc-framework-CoreWLAN",
        "pyobjc-framework-CoreLocation",
        "toml",
    ],
    entry_points={
        "console_scripts": [
            "netwatcher = src.cli:cli",
            "netwatcher-agent = src.watcher:main",
        ],
    },
)
