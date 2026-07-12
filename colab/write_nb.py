import json, os

nb = {
 "cells": [
  {
   "cell_type": "markdown",
   "source": ["# V7 Training",
    "","XGBoost Colab Notebook"]
  },
  {
   "cell_type": "code",
   "source": ["print("hello")"]
  }
 ],
 "nbformat": 4,
 "nbformat_minor": 4
}

with open("v7_test.ipynb", "w") as f:
    json.dump(nb, f, indent=1)
print("written")
