#include "src/net.h"
#include "src/version.h"

#include <stdio.h>

int main(void) {
    printf("app %s over %s\n", VERSION, net_scheme());
    return 0;
}
