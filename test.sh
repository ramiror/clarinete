#!/bin/bash

set -Eeux
time docker-compose build summarizer_test deduplicator_test
time docker-compose --project-name clarinete-test-summarizer run summarizer_test
time docker-compose --project-name clarinete-test-deduplicator run deduplicator_test
