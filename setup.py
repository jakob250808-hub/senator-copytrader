from setuptools import find_packages, setup


setup(
    name="senator-copytrader",
    version="0.1.0",
    description="Paper-only copy-trading prototype for disclosed US Senate trades",
    packages=find_packages("src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "senator-copytrader=senator_copytrader.cli:main",
        ]
    },
)
