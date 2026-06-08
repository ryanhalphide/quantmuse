from setuptools import setup, find_packages

setup(
    name="data_service",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'pandas',
        'numpy',
        'python-binance>=1.0.0',
        'websocket-client>=1.0.0',
        'websockets>=10.0',
        'aiohttp>=3.8.0',
        'alpha_vantage',
        'fastapi',
        'uvicorn',
        'redis',
        'requests',
        'textblob',
        'openpyxl'
    ],
    extras_require={
        'test': [
            'pytest',
            'pytest-cov',
            'pytest-asyncio'
        ],
        'ai': [
            'openai',
            'langchain',
            'langchain-openai',
            'langchain-community',
            'transformers',
            'torch',
            'sentence-transformers',
            'accelerate',
            'spacy',
            'nltk',
            'textblob',
            'scikit-learn',
            'wordcloud'
        ],
        'visualization': [
            'matplotlib>=3.5.0',
            'seaborn>=0.11.0',
            'plotly>=5.0.0',
            'streamlit>=1.20.0',
            'kaleido>=0.2.1'  # 用于Plotly静态图片导出
        ],
        'realtime': [
            'websockets>=10.0',
            'aiohttp>=3.8.0',
            'asyncio-mqtt>=0.11.0',
            'redis>=4.0.0'
        ],
        'web': [
            'fastapi',
            'uvicorn[standard]',
            'jinja2',
            'aiofiles'
        ],
        'kalshi': [
            'requests',
            'pandas',
            'cryptography>=41.0.0'  # required to sign authenticated trading requests
        ]
    }
) 