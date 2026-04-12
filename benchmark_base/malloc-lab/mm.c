/*
 * mm-naive.c - The fastest, least memory-efficient malloc package.
 *
 * In this naive approach, a block is allocated by simply incrementing
 * the brk pointer.  A block is pure payload. There are no headers or
 * footers.  Blocks are never coalesced or reused. Realloc is
 * implemented directly using mm_malloc and mm_free.
 *
 * NOTE TO STUDENTS: Replace this header comment with your own header
 * comment that gives a high level description of your solution.
 */
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include <unistd.h>
#include <string.h>

#include "mm.h"
#include "memlib.h"


int mm_init(void);
void *mm_malloc(size_t size);
void mm_free(void *ptr);
void *mm_realloc(void *ptr, size_t size);

static void *extend_heap(size_t words);
static void *coalesce(void *bp);
static void *find_fit(size_t asize);
static void place(void *bp, size_t asize);


/*********************************************************
 * NOTE TO STUDENTS: Before you do anything else, please
 * provide your team information in the following struct.
 ********************************************************/
team_t team = {
    /* Team name */
    "KRAFTON_JUNGLE-12-302-7-4",
    /* First member's full name */
    "Lee HaeGeon",
    /* First member's email address */
    "atgsisu@gmail.com",
    /* Second member's full name (leave blank if none) */
    "",
    /* Second member's email address (leave blank if none) */
    ""};

/* single word (4) or double word (8) alignment */
#define ALIGNMENT 8

/* rounds up to the nearest multiple of ALIGNMENT */
#define ALIGN(size) (((size) + (ALIGNMENT - 1)) & ~0x7)

#define SIZE_T_SIZE (ALIGN(sizeof(size_t)))

/* Basic contants and macros */
#define WSIZE               4           /* Word and header/footer size (bytes) */
#define DSIZE               8           /* Double word size (bytes) */
#define CHUNKSIZE           (1 << 12)   /* Extend heap by this amount (bytes) */

#define MAX(x, y)           ((x) > (y) ? (x) : (y))

/* Pack a size and allocated bit into a word */
#define PACK(size, alloc)   ((size) | (alloc))

/* Read and write a word at address p */
#define GET(p)              (*(unsigned int *) (p))
#define PUT(p, val)         (*(unsigned int *) (p) = (val))

/* Read the size and allocated fields from address p */
#define GET_SIZE(p)         (GET(p) & (~0x07))
#define GET_ALLOC(p)        (GET(p) & (0x01))

/* Given block ptr bp, compute address of its header and footer */
#define HDRP(bp)            ((char*) (bp) - WSIZE)
#define FTRP(bp)            ((char*) (bp) + GET_SIZE(HDRP(bp)) - DSIZE)

/* Given block ptr bp, compute address of next and previous blocks */
#define NEXT_BLKP(bp)       ((char*) (bp) + GET_SIZE(HDRP(bp)))
#define PREV_BLKP(bp)       ((char*) (bp) - GET_SIZE((char *)(bp) - DSIZE))

void * heap_listp = NULL;

/*
 * mm_init - initialize the malloc package.
 * @return 0 (success), -1(fail)
 */
int mm_init(void)
{
    /* 힙의 크기를 4 * WSIZE 만큼 늘린다. */
    heap_listp = mem_sbrk(4 * WSIZE);
    if (heap_listp == (void*) - 1) {
        return -1;
    }

    PUT(heap_listp, 0);                                         /* Aligment Padding */
    PUT(((char*) heap_listp) + (1 * WSIZE), PACK(DSIZE, 1));    /* Prologue header */
    PUT(((char*) heap_listp) + (2 * WSIZE), PACK(DSIZE, 1));    /* Prologue footer */
    PUT(((char*) heap_listp) + (3 * WSIZE), PACK(0, 1));        /* Epilogue header */

    /* head_listp 포인터는 Prologue header와 footer 사이에 위치시키기 */
    heap_listp += (2 * WSIZE);

    /* Extend the empty heap with a free block of CHUNKSIZE bytes */ 
    if (extend_heap(CHUNKSIZE/WSIZE) == NULL) {
        return -1;
    }
    return 0;
}

/*
 * mm_malloc - 
 */
void *mm_malloc(size_t size)
{
    size_t asize;
    size_t expendsize;
    char* bp;

    /* 이상한 요청 쳐내기 */
    if (size <= 0) {
        return  NULL;
    }
    /* 헤더, 푸터를 포함한 필요한 사이즈 asize 계산 */
    if (size <= DSIZE) {
        asize = DSIZE * 2;
    } else {
        asize = DSIZE * ((size 
                            + DSIZE         /* Header, Footer 공간 확보 */ 
                            + (DSIZE - 1)   /* DSIZE로 align 해주는 tactic */
                            ) / DSIZE);     
    }

    /* asize 크기 블록을 할당할 수 있는지 검색 */
    bp = find_fit(asize);
    if (bp != NULL) {
        place(bp, asize);
        return bp;
    }
    /* 없다면 큰 블록을 새롭게 할당받기 */
    expendsize = MAX(asize, CHUNKSIZE);
    bp = extend_heap(expendsize / WSIZE);
    if (bp == NULL) {
        return NULL;
    }
    place(bp, asize);
    return bp;
}

/*
 * mm_free - 
 */
void mm_free(void *ptr)
{
    unsigned int size;
    size = GET_SIZE(HDRP(ptr));
    // mark its header and footer free
    PUT(HDRP(ptr), PACK(size, 0));
    PUT(FTRP(ptr), PACK(size, 0));

    // call coalase
    coalesce(ptr);
}

/*
 * mm_realloc - Implemented simply in terms of mm_malloc and mm_free
 */
void *mm_realloc(void *ptr, size_t size)
{
    void *oldptr = ptr;
    void *newptr;
    size_t copySize;

    newptr = mm_malloc(size);
    if (newptr == NULL)
        return NULL;
    copySize = *(size_t *)((char *)oldptr - SIZE_T_SIZE);
    if (size < copySize)
        copySize = size;
    memcpy(newptr, oldptr, copySize);
    mm_free(oldptr);
    return newptr;
}


static void *extend_heap(size_t words)
{
    char* bp; // TODO. 나는 void*를 쓰는 줄 알았는데... 왜 char*를 써야 하는거지?
    size_t size;
    
    /* size를 8의 배수(Double word)로 맞추도록 계산(words 반올림) */
    size = (words % 2 == 0) ? words * WSIZE : (words + 1) * WSIZE;

    /* mem_sbrk로 heap size를 늘린다. */
    bp = mem_sbrk(size);
    if (bp == (void *) - 1) {
        return NULL; // TODO. 왜 -1 을 반환하면 안 돼? 왜 NULL 이어야 함?
    }

    /* 기존의 Epilogue header를 새로운 block의 header로 만든다. */
    PUT(HDRP(bp), PACK(size, 0));

    /* 새로운 block의 footer를 설정한다. */
    PUT(FTRP(bp), PACK(size, 0));

    /* 새로운 Epilogue header를 설정한다. */
    PUT(HDRP(NEXT_BLKP(bp)), PACK(0, 1));

    return coalesce(bp);
}

static void *coalesce(void *bp)
{
    size_t is_prev_allocated = GET_ALLOC(HDRP(PREV_BLKP(bp))); // TODO. 둘 다 int를 썼었다. 왜 int는 안 되는거지???
    size_t is_next_allocated = GET_ALLOC(HDRP(NEXT_BLKP(bp)));
    size_t size = GET_SIZE(HDRP(bp));
    /* Case 1: prev allocated, next allocated */
    if (is_prev_allocated && is_next_allocated) {
        return bp;
    }
    
    /* Case 2: prev allocated, next free */
    else if (is_prev_allocated && !is_next_allocated) {
        size += GET_SIZE(HDRP(NEXT_BLKP(bp)));
        PUT(HDRP(bp), PACK(size, 0));
        PUT(FTRP(bp), PACK(size, 0));
        return bp;
    }

    /* Case 3: prev free, next allocated */
    else if (!is_prev_allocated && is_next_allocated) {
        size += GET_SIZE(HDRP(PREV_BLKP(bp)));
        PUT(HDRP(PREV_BLKP(bp)), PACK(size, 0));
        PUT(FTRP(bp), PACK(size, 0));
        return PREV_BLKP(bp);
    }

    /* Case 4: prev free, next free */
    else // (!is_prev_allocated && !is_next_allocated) {
    {
        size += GET_SIZE(HDRP(PREV_BLKP(bp))) + GET_SIZE(HDRP(NEXT_BLKP(bp)));
        PUT(HDRP(PREV_BLKP(bp)), PACK(size, 0));
        PUT(FTRP(NEXT_BLKP(bp)), PACK(size, 0));
        return PREV_BLKP(bp);
    }

}


static void *find_fit(size_t asize)
{
    /* first fit을 구현했다. */
    /* heap_listp 를 사용한다. */
    char* bp = heap_listp;
    /* 거기서부터 해당하는 자리가 있는지 순차적으로 검색한다.*/
    bp = NEXT_BLKP(bp);
    while (1) {
        size_t size = GET_SIZE(HDRP(bp));
        if (size == 0) {
            break;
        }
        if (! GET_ALLOC(HDRP(bp)) && asize <= size) {
            return bp;
        }

        bp = NEXT_BLKP(bp);
    }
    /* 없다면 NULL을 반환한다. */
    return NULL;
}


static void place(void *bp, size_t asize)
{
    size_t original_size = GET_SIZE(HDRP(bp));
    
    PUT(HDRP(bp), PACK(asize, 1));
    PUT(FTRP(bp), PACK(asize, 1));
    if (original_size - asize < DSIZE * 2) {
        return;    
    }
    PUT(HDRP(NEXT_BLKP(bp)), PACK(original_size - asize, 0));
    PUT(FTRP(NEXT_BLKP(bp)), PACK(original_size - asize, 0));
}

