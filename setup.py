from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh.readlines()]

setup(
    name="knowlion",
    version="2.0.0",
    author="Yuzhe.Bi",
    author_email="380875458@qq.com",
    description="KnowLion - 基于动态图数据库构建的超图结构RAG知识库系统",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ThutmoseAI/knowlion",  # 替换为实际的仓库地址
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
)