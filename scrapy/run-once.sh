#!/bin/bash
set -Eeux

cd /scrapy
scrapy runspider -L WARNING clarinetear/spiders/clarin.py
scrapy runspider -L WARNING clarinetear/spiders/lanacion.py
