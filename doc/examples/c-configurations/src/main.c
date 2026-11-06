#include "greeting.h"

#include <stdio.h>

int main(void) {
    print_greeting();
    puts("built as " BUILD_NAME);
    return 0;
}
