#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "src/common/message.h"

int main(void)
{
    char *text = message_encode("world");
    char *name = message_decode(text);
    int passed = name && strcmp(name, "world") == 0;
    puts(passed ? "message: ok" : "message: FAILED");
    free(text);
    free(name);
    return passed ? 0 : 1;
}
