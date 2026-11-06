#include <stdio.h>
#include <stdlib.h>
#include "src/server/reply.h"

int main(void)
{
    char request[256];
    if (!fgets(request, sizeof request, stdin))
        return 1;
    char *text = reply(request);
    puts(text);
    free(text);
    return 0;
}
