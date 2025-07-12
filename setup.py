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
        "pyobjc-framework-SystemConfiguration",
        "toml",
    ],
    entry_points={
        "console_scripts": [
            "netwatcher=src.cli:cli",
            "netwatcher-agent=src.watcher:main",
        ],
    },
    python_requires=">=3.9",
    author="Network Watcher Contributors",
    description="Automatic network configuration manager for macOS",
    long_description="A modern macOS utility that automatically reconfigures system settings when your network environment changes.",
    url="https://github.com/dfelicia/netwatcher-py",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: MacOS X",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Networking",
        "Topic :: System :: Systems Administration",
    ],
)
