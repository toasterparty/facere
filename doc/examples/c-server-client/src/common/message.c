#include <stdlib.h>
#include <string.h>
#include "src/common/codec/checksum.h"
#include "src/common/message.h"
#include "cJSON.h"

char *message_encode(const char *name)
{
    cJSON *msg = cJSON_CreateObject();
    cJSON_AddStringToObject(msg, "hello", name);
    cJSON_AddNumberToObject(msg, "sum", checksum(name));
    char *text = cJSON_PrintUnformatted(msg);
    cJSON_Delete(msg);
    return text;
}

char *message_decode(const char *text)
{
    cJSON *msg = cJSON_Parse(text);
    const cJSON *name = cJSON_GetObjectItemCaseSensitive(msg, "hello");
    const cJSON *sum = cJSON_GetObjectItemCaseSensitive(msg, "sum");
    char *result = NULL;
    if (cJSON_IsString(name) && cJSON_IsNumber(sum) && (unsigned int)sum->valuedouble == checksum(name->valuestring))
        result = strdup(name->valuestring);
    cJSON_Delete(msg);
    return result;
}
