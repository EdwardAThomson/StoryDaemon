"""Setup configuration for StoryDaemon."""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="storydaemon",
    version="0.1.0",
    author="Edward A. Thomson",
    description="Agentic novel generation system with emergent narrative",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/EdwardAThomson/StoryDaemon",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.11",
    install_requires=[
        "typer>=0.9.0",
        "pyyaml>=6.0.0",
        "jsonschema>=4.0.0",
        "openai>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "novel=novel_agent.cli.main:main",
        ],
    },
)
