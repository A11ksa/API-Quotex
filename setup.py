from pathlib import Path
from setuptools import setup, find_packages

README = Path(__file__).with_name("README.md")
long_description = README.read_text(encoding="utf-8") if README.exists() else ""

setup(
    name="api_quotex",
    version="2.0.0",
    author="Ahmed",
    author_email="ar123ksa@gmail.com",
    description="Professional Async WebSocket API client for Quotex with Playwright-based login helper",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/A11ksa/API-Quotex",
    project_urls={
        "Homepage": "https://github.com/A11ksa/API-Quotex",
        "Issues": "https://github.com/A11ksa/API-Quotex/issues",
    },
    packages=find_packages(exclude=("tests*", "examples*")),
    include_package_data=True,
    install_requires=[
        "websockets>=11.0.3",
        "loguru>=0.7.0",
        "pandas>=1.3.0",
        "requests>=2.26.0",
        # Playwright for automated, browser-based login to Quotex
        "playwright>=1.44.0",
    ],
    extras_require={
        "dev": ["pytest>=7.0", "flake8>=6.0", "black>=23.0"],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    keywords=["quotex", "trading", "websocket", "asyncio", "playwright"],
    python_requires=">=3.8",
)
