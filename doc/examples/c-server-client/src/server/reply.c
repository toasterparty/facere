#include <string.h>
#include "src/common/message.h"
#include "src/server/reply.h"

char *reply(char *request)
{
    request[strcspn(request, "\n")] = '\0';
    return message_encode(request);
}
