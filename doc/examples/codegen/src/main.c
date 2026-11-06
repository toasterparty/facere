#include <stdio.h>
#include <string.h>
#include "messages/greeting.h"
#include "src/keywords.h"

int session_open(const char *user, int attempt);

int main(int argc, char **argv)
{
    const char *word = argc > 1 ? argv[1] : "greeting";
    const struct keyword *keyword = keyword_find(word, strlen(word));
    if (!keyword)
        return 1;
    struct greeting message = { word };
    printf("%s: token %d, valid %d, session %d\n", word, keyword->token, greeting_validate(&message), session_open("world", 1));
    return 0;
}
