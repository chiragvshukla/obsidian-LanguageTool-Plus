# Custom LanguageTool image: adds our own German rules and spelling additions
# on top of the community image. LanguageTool itself is unmodified source.
ARG LANGUAGETOOL_IMAGE=erikvl87/languagetool:latest
FROM ${LANGUAGETOOL_IMAGE}

USER root

# Global spelling additions (one word per line). Kept in the repo so changes
# are reviewable. The runtime path is documented in docs/ARCHITECTURE.md.
COPY docker/languagetool/spelling-de.txt /tmp/spelling-de.txt
RUN cat /tmp/spelling-de.txt >> /LanguageTool/org/languagetool/resource/de/hunspell/spelling.txt \
    && rm /tmp/spelling-de.txt

# Custom grammar rules are loaded by LanguageTool 6.0+ from this path.
COPY rules/grammar_custom.xml /LanguageTool/org/languagetool/rules/de/grammar_custom.xml

USER languagetool