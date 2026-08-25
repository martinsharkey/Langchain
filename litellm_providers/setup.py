"""
Setup script for litellm_providers — standalone multi-provider LLM router.

Install directly from GitHub:
    pip install git+https://github.com/martinsharkey/langchain.git

Or install locally:
    pip install -e litellm_providers/

Usage:
    from litellm_providers import get_llm, get_configured_providers
    llm = get_llm()
    response = llm.invoke("Hello!")
"""

from setuptools import setup, find_packages

setup(
    name="litellm_providers",
    version="1.0.0",
    description="Multi-provider LLM router with automatic fallback across 15+ free LLM providers",
    long_description=open("README.md").read() if __import__("os").path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="Martin Sharkey",
    url="https://github.com/martinsharkey/langchain",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "litellm>=1.40.0",
        "langchain-litellm>=0.7.0",
        "langchain-core>=0.3.0",
        "python-dotenv>=1.0.0",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
