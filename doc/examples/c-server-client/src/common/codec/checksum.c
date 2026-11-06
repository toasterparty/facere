#include "src/common/codec/checksum.h"

unsigned int checksum(const char *text)
{
    unsigned int sum = 5381;
    for (; *text; text++)
        sum = (sum * 33 + (unsigned char)*text) & 0xffffu;
    return sum;
}
