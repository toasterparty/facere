#include <stdio.h>
#include <stdlib.h>
#include "src/client/render.h"
#include "src/common/message.h"

int main(void)
{
    char response[256];
    if (!fgets(response, sizeof response, stdin))
        return 1;
    char *name = message_decode(response);
    if (!name)
        return 1;
    render(name);
    free(name);
    return 0;
}
