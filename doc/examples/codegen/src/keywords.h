#ifndef SRC_KEYWORDS_H
#define SRC_KEYWORDS_H

#include <stddef.h>

struct keyword {
    const char *name;
    int token;
};

const struct keyword *keyword_find(const char *text, size_t length);

#endif
