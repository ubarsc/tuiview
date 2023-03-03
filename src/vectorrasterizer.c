/*
 This file is part of 'TuiView' - a simple Raster viewer
 Copyright (C) 2012  Sam Gillingham

 This program is free software; you can redistribute it and/or
 modify it under the terms of the GNU General Public License
 as published by the Free Software Foundation; either version 2
 of the License, or (at your option) any later version.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program; if not, write to the Free Software
 Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
*/

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "numpy/arrayobject.h"
#include <string.h>
#include <stdlib.h>

#include "ogr_api.h"

/* define WKB_BYTE_ORDER depending on endian setting
 from pyconfig.h */
#if WORDS_BIGENDIAN == 1
    #define WKB_BYTE_ORDER wkbXDR
#else
    #define WKB_BYTE_ORDER wkbNDR
#endif

/* do a memcpy rather than cast and access so we work on SPARC etc with aligned reads */
#define READ_WKB_VAL(n, p)  memcpy(&n, p, sizeof(n)); p += sizeof(n);

/* for burning points as a cross so they can be seen */
#define HALF_CROSS_SIZE 5

/* release the GIL when we know the WKB is bigger than this size in bytes */
#define GIL_WKB_SIZE_THRESHOLD 1024

/* This is used when filling */
/* There is a linked list of these 'slabs' that contain corners for the rings for each feature */
/* used by fillPoly() below */
typedef struct sPolycornersStruct
{
    double *pPolyX; /* array of x coords for the corners */
    double *pPolyY; /* array of y coords for the corners */
    int nPolyCorners; /* number of corners */
    struct sPolycornersStruct *pNext; /* next slab (or NULL) */
} PolycornersSlab;

typedef struct 
{
    PyArrayObject *pArray;
    int nLineWidth;
    double *pExtents;
    double dMetersPerPix;
    npy_intp nXSize;
    npy_intp nYSize;
    int bFill;
    int nHalfCrossSize;
    /* below is for bFill */
    struct sPolycornersStruct *pFirstSlab; /* linked list */
    double dMinY;   /* min y coord for corners */
    double dMaxY;   /* max y coord for corners */
} VectorWriterData;

static VectorWriterData* VectorWriter_create(PyArrayObject *pArray, double *pExtents, 
        int nLineWidth, int bFill, int nHalfCrossSize)
{
    VectorWriterData *pData;

    pData = (VectorWriterData*)malloc(sizeof(VectorWriterData));

    pData->pArray = pArray;
    pData->pExtents = pExtents;
    pData->nLineWidth = nLineWidth;
    if( pData->nLineWidth < 0 )
        pData->nLineWidth = 0;
    pData->nYSize = PyArray_DIMS(pArray)[0];
    pData->nXSize = PyArray_DIMS(pArray)[1];
    pData->dMetersPerPix = (pExtents[2] - pExtents[0]) / ((double)pData->nXSize);
    pData->bFill = bFill;
    pData->nHalfCrossSize = nHalfCrossSize;
    pData->pFirstSlab = NULL;
    
    return pData;
}

static void VectorWriter_destroy(VectorWriterData *pData)
{
    /* Note: slabs freed in processAll() */
    free(pData);
}

static void VectorWriter_plot(VectorWriterData *pData, int x, int y)
{
    /*fprintf(stderr, "plot %d %d\n", x, y);*/
    double dSize;
    int nNorthWestPixels, nSouthEastPixels;
    int tlx, tly, brx, bry;

    if( pData->nLineWidth == 1 )
    {
        if( ( x >= 0 ) && ( x < pData->nXSize ) && ( y >= 0 ) && ( y < pData->nYSize ) )
        {
            *((npy_uint8*)PyArray_GETPTR2(pData->pArray, y, x)) = 1;
        }
    }
    else if( pData->nLineWidth > 1 )
    {
        /* do some dodgy maths to work out how many pixels either side
         since if it is an even number we err to the north west*/
        dSize = ((double)(pData->nLineWidth-1)) / 2.0;
        nNorthWestPixels = ceil(dSize);
        nSouthEastPixels = floor(dSize);
        tlx = x - nNorthWestPixels;
        tly = y - nNorthWestPixels;
        brx = x + nSouthEastPixels;
        bry = y + nSouthEastPixels;
        for( x = tlx; x <= brx; x++ )
        {
            for( y = tly; y <= bry; y++ )
            {
                if( ( x >= 0 ) && ( x < pData->nXSize ) && ( y >= 0 ) && ( y < pData->nYSize ) )
                {
                    *((npy_uint8*)PyArray_GETPTR2(pData->pArray, y, x)) = 1;
                }
            }
        }
    }
}

/* adapted from http://roguebasin.roguelikedevelopment.org/index.php?title=Bresenham%27s_Line_Algorithm#C.2B.2B */
static void VectorWriter_bresenham(VectorWriterData *pData, int x1, int y1, int x2, int y2)
{
    int delta_x, delta_y, error;
    signed char ix, iy;

    delta_x = x2 - x1;
    /* if x1 == x2, then it does not matter what we set here*/
    ix = (delta_x > 0) - (delta_x < 0);
    delta_x = abs(delta_x) << 1;
 
    delta_y = y2 - y1;
    /* if y1 == y2, then it does not matter what we set here*/
    iy = (delta_y > 0) - (delta_y < 0);
    delta_y = abs(delta_y) << 1;
 
    VectorWriter_plot(pData, x1, y1);
 
    if (delta_x >= delta_y)
    {
        /* error may go below zero*/
        error = delta_y - (delta_x >> 1);
 
        while (x1 != x2)
        {
            if ((error >= 0) && (error || (ix > 0)))
            {
                error -= delta_x;
                y1 += iy;
            }
            /* else do nothing*/
 
            error += delta_y;
            x1 += ix;
 
            VectorWriter_plot(pData, x1, y1);
        }
    }
    else
    {
        /* error may go below zero*/
        error = delta_x - (delta_y >> 1);
 
        while (y1 != y2)
        {
            if ((error >= 0) && (error || (iy > 0)))
            {
                error -= delta_y;
                x1 += ix;
            }
            /* else do nothing*/
 
            error += delta_x;
            y1 += iy;
 
            VectorWriter_plot(pData, x1, y1);
        }
    }
}

/* only called for points */
static void VectorWriter_burnPoint(VectorWriterData *pData, double dx, double dy)
{
    int nx, ny, x, y;

    nx = (dx - pData->pExtents[0]) / pData->dMetersPerPix;
    ny = (pData->pExtents[1] - dy) / pData->dMetersPerPix;
    if( pData->nHalfCrossSize == 1 )
    {
        VectorWriter_plot(pData, nx, ny);
    }
    else if( pData->nHalfCrossSize > 1 )
    {
        /* burn a cross*/
        for( x = (nx - pData->nHalfCrossSize); x < (nx + pData->nHalfCrossSize); x++)
            VectorWriter_plot(pData, x, ny);
        for( y = (ny - pData->nHalfCrossSize); y < (ny + pData->nHalfCrossSize); y++)
            VectorWriter_plot(pData, nx, y);
    }
}

static void VectorWriter_burnLine(VectorWriterData *pData, double dx1, double dy1, double dx2, double dy2)
{
    int nx1, ny1, nx2, ny2;

    /* note: not round as that can pop it into the neighbouring pixel */
    nx1 = (dx1 - pData->pExtents[0]) / pData->dMetersPerPix;
    ny1 = (pData->pExtents[1] - dy1) / pData->dMetersPerPix;
    nx2 = (dx2 - pData->pExtents[0]) / pData->dMetersPerPix;
    ny2 = (pData->pExtents[1] - dy2) / pData->dMetersPerPix;
    VectorWriter_bresenham(pData, nx1, ny1, nx2, ny2);
}

static const unsigned char* VectorWriter_processPoint(VectorWriterData *pData, const unsigned char *pWKB, int hasz)
{
    double x, y;

    READ_WKB_VAL(x, pWKB)
    READ_WKB_VAL(y, pWKB)
    if(hasz)
    {
        pWKB += sizeof(double);
    }

    VectorWriter_burnPoint(pData, x, y);
    return pWKB;
}

static const unsigned char* VectorWriter_processLineString(VectorWriterData *pData, const unsigned char *pWKB, int hasz)
{
    GUInt32 nPoints, n;
    double dx1, dy1, dx2, dy2;

    READ_WKB_VAL(nPoints, pWKB)
    if( nPoints > 0 )
    {
        if( pData->nLineWidth > 0 )
        {
            /* get the first point */
            READ_WKB_VAL(dx1, pWKB)
            READ_WKB_VAL(dy1, pWKB)
            if(hasz)
            {
                pWKB += sizeof(double);
            }
            for( n = 1; n < nPoints; n++ )
            {
                READ_WKB_VAL(dx2, pWKB)
                READ_WKB_VAL(dy2, pWKB)
                if(hasz)
                {
                    pWKB += sizeof(double);
                }
                VectorWriter_burnLine(pData, dx1, dy1, dx2, dy2);
                /* set up for next one */
                dx1 = dx2;
                dy1 = dy2;
            }
        }
        else
        {
            /* skip */
            pWKB += nPoints * (sizeof(double) * 2);
            if(hasz)
            {
                pWKB += nPoints * sizeof(double);
            }
        }
    }
    return pWKB;
}

/* taken from https://alienryderflex.com/polygon_fill/ */
static void fillPoly(VectorWriterData *pData)
{
    int nodes, i, j, totalPolycorners = 0, nx, ny;
    double swap, *nodeX, pixelX, pixelY;
    struct sPolycornersStruct *pCurr;
    
    /* find the total corners for all the slabs */
    pCurr = pData->pFirstSlab;
    while( pCurr != NULL )
    {
        totalPolycorners += pCurr->nPolyCorners;
        pCurr = pCurr->pNext;
    }
    
    if( totalPolycorners < 2 )
    {
        return;
    }
    
    nodeX = (double*)malloc(totalPolycorners * sizeof(double));
    if( nodeX == NULL )
    {
        fprintf(stderr, "Allocation for fill failed\n");
        return;
    }
    
    /* Just process the area we are using */
    for( ny = 0; ny < pData->nYSize; ny++ )
    {
        pixelY = pData->pExtents[1] - (ny * pData->dMetersPerPix);
        if( (pixelY < pData->dMinY) || (pixelY > pData->dMaxY) )
        {
            // outside extent of corners we have collected. bail.
            continue;
        }

        /*  Build a list of nodes. For each slab separately */
        nodes = 0; 
        pCurr = pData->pFirstSlab;
        while( pCurr != NULL )
        {
            j = pCurr->nPolyCorners - 1;
            for( i = 0; i < pCurr->nPolyCorners; i++) 
            {
                if( (pCurr->pPolyY[i] < pixelY && pCurr->pPolyY[j] >= pixelY)
                    || (pCurr->pPolyY[j] < pixelY && pCurr->pPolyY[i] >= pixelY)) 
                {
                    nodeX[nodes++] = (pCurr->pPolyX[i]+(pixelY-pCurr->pPolyY[i])/(pCurr->pPolyY[j]-pCurr->pPolyY[i])*(pCurr->pPolyX[j]-pCurr->pPolyX[i])); 
                }
                j = i; 
            }
            pCurr = pCurr->pNext;
        }

        /* Sort the nodes, via a simple Bubble sort. */
        i = 0;
        while( i < nodes - 1 ) 
        {
            if( nodeX[i] > nodeX[i+1] )
            {
                swap = nodeX[i]; 
                nodeX[i] = nodeX[i+1]; 
                nodeX[i+1] = swap; 
                if( i ) i--;
            }
            else 
            {
                i++; 
            }
        }

        /*  Fill the pixels between node pairs. */
        for( i = 0; i < nodes; i += 2) 
        {
            /* extents are (tlx, tly, brx, bry) */
            if( nodeX[i] >= pData->pExtents[2]) break;
            if( nodeX[i+1] > pData->pExtents[0] ) {
                if( nodeX[i] < pData->pExtents[0] ) nodeX[i] = pData->pExtents[0];
                if( nodeX[i+1] > pData->pExtents[2]) nodeX[i+1] = pData->pExtents[2];
                for( pixelX = nodeX[i]; pixelX < nodeX[i+1]; pixelX += pData->dMetersPerPix) 
                { 
                    nx = (pixelX - pData->pExtents[0]) / pData->dMetersPerPix;
                    /* do range check again as we might not be within the image */
                    if( (nx >= 0) && (nx < pData->nXSize)) 
                    {
                        *((npy_uint8*)PyArray_GETPTR2(pData->pArray, ny, nx)) = 1;
                    }
                }
            }
        }
    }
}

/* same as processLineString, but closes ring */
static const unsigned char* VectorWriter_processLinearRing(VectorWriterData *pData, const unsigned char *pWKB, int hasz)
{
    GUInt32 nPoints, n;
    double dx1, dy1, dx2, dy2;
    double dFirstX, dFirstY;
    struct sPolycornersStruct *pSlab = NULL, *pLastSlab;
    int bCornerAllocationOK = 0;

    READ_WKB_VAL(nPoints, pWKB)
    if( nPoints > 0 )
    {
        /* get the first point */
        READ_WKB_VAL(dx1, pWKB)
        READ_WKB_VAL(dy1, pWKB)
        if(hasz)
        {
            pWKB += sizeof(double);
        }
        dFirstX = dx1;
        dFirstY = dy1;
        
        if( pData->bFill )
        {
            /* create buffer for fill */
            pSlab = (struct sPolycornersStruct*)malloc(sizeof(struct sPolycornersStruct));
            pSlab->pPolyX = (double*)malloc(sizeof(double) * nPoints);
            pSlab->pPolyY = (double*)malloc(sizeof(double) * nPoints);
            if( (pSlab != NULL) && (pSlab->pPolyX != NULL) && (pSlab->pPolyY != NULL) )
            {
                /* If any of the allocations above fail then we don't add the slab */
                bCornerAllocationOK = 1;
                /* first point */
                pSlab->pPolyX[0] = dFirstX;
                pSlab->pPolyY[0] = dFirstY;
                pSlab->nPolyCorners = 1;
                pSlab->pNext = NULL;
            
                if( pData->pFirstSlab == NULL )
                {
                    /* first slab - init range */
                    pData->pFirstSlab = pSlab;
                    pData->dMinY = dFirstY;
                    pData->dMaxY = dFirstY;
                }
                else
                {
                    pLastSlab = pData->pFirstSlab;
                    while( pLastSlab->pNext != NULL )
                    {
                        pLastSlab = pLastSlab->pNext;
                    }
                    pLastSlab->pNext = pSlab;
                }
            }
        }

        for( n = 1; n < nPoints; n++ )
        {
            READ_WKB_VAL(dx2, pWKB)
            READ_WKB_VAL(dy2, pWKB)
            if(hasz)
            {
                pWKB += sizeof(double);
            }
            if( pData->nLineWidth > 0 )
            {
                VectorWriter_burnLine(pData, dx1, dy1, dx2, dy2);
            }
            if( pData->bFill && bCornerAllocationOK )
            {
                pSlab->pPolyX[pSlab->nPolyCorners] = dx2;
                pSlab->pPolyY[pSlab->nPolyCorners] = dy2;
                pSlab->nPolyCorners++;
                if( dy2 < pData->dMinY ) 
                    pData->dMinY = dy2;
                if( dy2 > pData->dMaxY )
                    pData->dMaxY = dy2;
            }

            /* set up for next one */
            dx1 = dx2;
            dy1 = dy2;
        }
        /* close it*/
        if( pData->nLineWidth > 0 )
        {
            VectorWriter_burnLine(pData, dx1, dy1, dFirstX, dFirstY);
        }
    }
        
    return pWKB;
}

static const unsigned char* VectorWriter_processPolygon(VectorWriterData *pData, const unsigned char *pWKB, int hasz)
{
    GUInt32 nRings, n;

    READ_WKB_VAL(nRings, pWKB)
    for( n = 0; n < nRings; n++ )
    {
        pWKB = VectorWriter_processLinearRing(pData, pWKB, hasz);
    }
    return pWKB;
}

static const unsigned char* VectorWriter_processMultiPoint(VectorWriterData *pData, const unsigned char *pWKB, int hasz)
{
    GUInt32 nPoints, n;

    READ_WKB_VAL(nPoints, pWKB)
    for( n = 0; n < nPoints; n++ )
    {
        pWKB++; /* ignore endian */
        pWKB += sizeof(GUInt32); /* ignore type (must be point) */
        pWKB = VectorWriter_processPoint(pData, pWKB, hasz);
    }
    return pWKB;
}

static const unsigned char* VectorWriter_processMultiLineString(VectorWriterData *pData, const unsigned char *pWKB, int hasz)
{
    GUInt32 nLines, n;

    READ_WKB_VAL(nLines, pWKB)
    for( n = 0; n < nLines; n++ )
    {
        pWKB++; /* ignore endian */
        pWKB += sizeof(GUInt32); /* ignore type */
        pWKB = VectorWriter_processLineString(pData, pWKB, hasz);
    }
    return pWKB;
}

static const unsigned char* VectorWriter_processMultiPolygon(VectorWriterData *pData, const unsigned char *pWKB, int hasz)
{
    GUInt32 nPolys, n;

    READ_WKB_VAL(nPolys, pWKB)
    for( n = 0; n < nPolys; n++ )
    {
        pWKB++; /* ignore endian */
        pWKB += sizeof(GUInt32); /* ignore type */
        pWKB = VectorWriter_processPolygon(pData, pWKB, hasz);
    }
    return pWKB;
}

static const unsigned char* VectorWriter_processWKB(VectorWriterData *pData, const unsigned char *pCurrWKB);

static const unsigned char* VectorWriter_processGeometryCollection(VectorWriterData *pData, const unsigned char *pWKB)
{
    GUInt32 nGeoms, n;

    READ_WKB_VAL(nGeoms, pWKB)
    for( n = 0; n < nGeoms; n++ )
    {
        /* start again! */
        pWKB = VectorWriter_processWKB(pData, pWKB);
    }
    return pWKB;
}

static const unsigned char* VectorWriter_processWKB(VectorWriterData *pData, const unsigned char *pCurrWKB)
{
    GUInt32 nType;

    /* ignore byte order (should be native) */
    pCurrWKB++;
    READ_WKB_VAL(nType, pCurrWKB)
    switch(nType)
    {
    case wkbPoint:
        pCurrWKB = VectorWriter_processPoint(pData, pCurrWKB, 0);
        break;
    case wkbPoint25D:
        pCurrWKB = VectorWriter_processPoint(pData, pCurrWKB, 1);
        break;
    case wkbLineString:
        pCurrWKB = VectorWriter_processLineString(pData, pCurrWKB, 0);
        break;
    case wkbLineString25D:
        pCurrWKB = VectorWriter_processLineString(pData, pCurrWKB, 1);
        break;
    case wkbPolygon:
        pCurrWKB = VectorWriter_processPolygon(pData, pCurrWKB, 0);
        break;
    case wkbPolygon25D:
        pCurrWKB = VectorWriter_processPolygon(pData, pCurrWKB, 1);
        break;
    case wkbMultiPoint:
        pCurrWKB = VectorWriter_processMultiPoint(pData, pCurrWKB, 0);
        break;
    case wkbMultiPoint25D:
        pCurrWKB = VectorWriter_processMultiPoint(pData, pCurrWKB, 1);
        break;
    case wkbMultiLineString:
        pCurrWKB = VectorWriter_processMultiLineString(pData, pCurrWKB, 0);
        break;
    case wkbMultiLineString25D:
        pCurrWKB = VectorWriter_processMultiLineString(pData, pCurrWKB, 1);
        break;
    case wkbMultiPolygon:
        pCurrWKB = VectorWriter_processMultiPolygon(pData, pCurrWKB, 0);
        break;
    case wkbMultiPolygon25D:
        pCurrWKB = VectorWriter_processMultiPolygon(pData, pCurrWKB, 1);
        break;
    case wkbGeometryCollection:
    case wkbGeometryCollection25D:
        pCurrWKB = VectorWriter_processGeometryCollection(pData, pCurrWKB);
        break;
    case wkbNone:
        /* pure attribute records */
        break;
    default:
        fprintf( stderr, "Unknown WKB code %d\n", nType);
        break;
    }
    return pCurrWKB;
}

static const void VectorWriter_processAll(VectorWriterData *pData, const unsigned char *pWKB)
{
    struct sPolycornersStruct *tmp, *head;

    VectorWriter_processWKB(pData, pWKB);
    
    if( pData->bFill && (pData->pFirstSlab != NULL) )
    {
        fillPoly(pData);
        
        /* Now we can free all the slabs so they don't get confused with the next layer */
        head = pData->pFirstSlab;
        while( head != NULL )
        {
            tmp = head;
            head = head->pNext;
            if( tmp->pPolyX != NULL )
                free(tmp->pPolyX);
            if( tmp->pPolyY != NULL )
                free(tmp->pPolyY);
            free(tmp);
        }
        pData->pFirstSlab = NULL;
    }
}

/* bit of a hack here - this is what a SWIG object looks
 like. It is only defined in the source file so we copy it here*/
typedef struct {
  PyObject_HEAD
  void *ptr;
  /* the rest aren't needed (and a hassle to define here)
  swig_type_info *ty;
  int own;
  PyObject *next;*/
} SwigPyObject;

/* in the ideal world I would use SWIG_ConvertPtr etc
 but to avoid the whole dependence on SWIG headers
 and needing to reach into the GDAL source to get types etc
 I happen to know the 'this' attribute is a pointer to 
 OGRLayerShadow which is actually a pointer
 to a SwigPyObject whose ptr field is a pointer to a
 OGRLayer. Phew. 
 Given a python object this function returns the underlying
 pointer. Returns NULL on failure (exception string already set)*/
void *getUnderlyingPtrFromSWIGPyObject(PyObject *pObj, PyObject *pException)
{
    PyObject *pThisAttr; /* the 'this' field */
    SwigPyObject *pSwigThisAttr;
    void *pUnderlying;

    pThisAttr = PyObject_GetAttrString(pObj, "this");
    if( pThisAttr == NULL )
    {
        PyErr_SetString(pException, "object does not appear to be a swig type");
        return NULL;
    }

    /* i think it is safe to do this since pObj is still around*/
    Py_DECREF(pThisAttr);

    /* convert this to a SwigPyObject*/
    pSwigThisAttr = (SwigPyObject*)pThisAttr;

    /* get the ptr field*/
    pUnderlying = pSwigThisAttr->ptr;
    if( pUnderlying == NULL )
    {
        PyErr_SetString(pException, "underlying object is NULL");
        return NULL;
    }

    return pUnderlying;
}


/* An exception object for this module */
/* created in the init function */
struct VectorRasterizerState
{
    PyObject *error;
};

#define GETSTATE(m) ((struct VectorRasterizerState*)PyModule_GetState(m))

/* Helper function */
/* Gets the value of the module variable HALF_CROSS_SIZE to use as default */
int GetDefaultHalfCrossSize(PyObject *self)
{
    PyObject *pObj;
    int nHalfCrossSize = HALF_CROSS_SIZE, n;
    
    pObj = PyObject_GetAttrString(self, "HALF_CROSS_SIZE");
    if( pObj != NULL )
    {
        n = PyLong_AsLong(pObj);
        Py_DECREF(pObj);
        if( (n == -1 ) && PyErr_Occurred() )
            return nHalfCrossSize;
        else
            nHalfCrossSize = n;
    }
    
    return nHalfCrossSize;
}

static PyObject *vectorrasterizer_rasterizeLayer(PyObject *self, PyObject *args, PyObject *kwds)
{
    PyObject *pPythonLayer; /* of type ogr.Layer*/
    PyObject *pBBoxObject; /* must be a sequence*/
    int nXSize, nYSize, nLineWidth;
    const char *pszSQLFilter;
    void *pPtr;
    OGRLayerH hOGRLayer;
    double adExtents[4];
    PyObject *o, *pOutArray;
    npy_intp dims[2];
    VectorWriterData *pWriter;
    OGRFeatureH hFeature;
    int nCurrWKBSize;
    unsigned char *pCurrWKB;
    OGRGeometryH hGeometry;
    int nNewWKBSize;
    unsigned char *pNewWKB;
    int n, bFill = 0, nHalfCrossSize = GetDefaultHalfCrossSize(self);
    NPY_BEGIN_THREADS_DEF;

    char *kwlist[] = {"ogrlayer", "boundingbox", "xsize", "ysize", 
            "linewidth", "sql", "fill", "halfCrossSize", NULL};
    if( !PyArg_ParseTupleAndKeywords(args, kwds, "OOiiiz|ii:rasterizeLayer", kwlist, 
            &pPythonLayer, &pBBoxObject, &nXSize, &nYSize, &nLineWidth, 
            &pszSQLFilter, &bFill, &nHalfCrossSize))
        return NULL;

    pPtr = getUnderlyingPtrFromSWIGPyObject(pPythonLayer, GETSTATE(self)->error);
    if( pPtr == NULL )
        return NULL;
    hOGRLayer = (OGRLayerH)pPtr;

    if( !PySequence_Check(pBBoxObject))
    {
        PyErr_SetString(GETSTATE(self)->error, "second argument must be a sequence");
        return NULL;
    }

    if( PySequence_Size(pBBoxObject) != 4 )
    {
        PyErr_SetString(GETSTATE(self)->error, "sequence must have 4 elements");
        return NULL;
    }

    for( n = 0; n < 4; n++ )
    {
        o = PySequence_GetItem(pBBoxObject, n);
        if( !PyFloat_Check(o) )
        {
            PyErr_SetString(GETSTATE(self)->error, "Must be a sequence of floats" );
            Py_DECREF(o);
            return NULL;
        }
        adExtents[n] = PyFloat_AsDouble(o);
        Py_DECREF(o);
    }

    /* create output array - all 0 to begin with */
    dims[0] = nYSize;
    dims[1] = nXSize;
    pOutArray = PyArray_ZEROS(2, dims, NPY_UINT8, 0);
    if( pOutArray == NULL )
    {
        PyErr_SetString(GETSTATE(self)->error, "Unable to allocate array" );
        return NULL;
    }
    
    /* Always release GIL as we don't know number of features/how big the WKBs are */
    NPY_BEGIN_THREADS;

    /* set up the object that does the writing */
    pWriter = VectorWriter_create((PyArrayObject*)pOutArray, adExtents, nLineWidth, bFill, nHalfCrossSize);
    
    /* set the spatial filter to the extent */
    OGR_L_SetSpatialFilterRect(hOGRLayer, adExtents[0], adExtents[1], adExtents[2], adExtents[3]);
    /* set the attribute filter (if None/NULL resets) */
    OGR_L_SetAttributeFilter(hOGRLayer, pszSQLFilter);

    OGR_L_ResetReading(hOGRLayer);

    nCurrWKBSize = 0;
    pCurrWKB = NULL;

    while( ( hFeature = OGR_L_GetNextFeature(hOGRLayer)) != NULL )
    {
        hGeometry = OGR_F_GetGeometryRef(hFeature);
        if( hGeometry != NULL )
        {
            /* how big a buffer do we need? Grow if needed */
            nNewWKBSize = OGR_G_WkbSize(hGeometry);
            if( nNewWKBSize > nCurrWKBSize )
            {
                pNewWKB = (unsigned char*)realloc(pCurrWKB, nNewWKBSize);
                if( pNewWKB == NULL )
                {
                    /* realloc failed - bail out */
                    /* according to man page original not freed */
                    free(pCurrWKB);
                    OGR_F_Destroy(hFeature);
                    VectorWriter_destroy(pWriter);
                    NPY_END_THREADS;
                    Py_DECREF(pOutArray);
                    PyErr_SetString(GETSTATE(self)->error, "memory allocation failed");
                    return NULL;
                }
                else
                {
                    pCurrWKB = pNewWKB;
                    nCurrWKBSize = nNewWKBSize;
                }
            }
            /* read it in */
            OGR_G_ExportToWkb(hGeometry, WKB_BYTE_ORDER, pCurrWKB);
            /* write it to array */
            VectorWriter_processAll(pWriter, pCurrWKB);
        }

        OGR_F_Destroy(hFeature);
    }
    free( pCurrWKB );
    VectorWriter_destroy(pWriter);
    NPY_END_THREADS;

    return pOutArray;
}

static PyObject *vectorrasterizer_rasterizeFeature(PyObject *self, PyObject *args, PyObject *kwds)
{
    PyObject *pPythonFeature; /* of type ogr.Feature*/
    PyObject *pBBoxObject; /* must be a sequence*/
    int nXSize, nYSize, nLineWidth;
    void *pPtr;
    OGRFeatureH hOGRFeature;
    double adExtents[4];
    PyObject *o;
    npy_intp dims[2];
    PyObject *pOutArray;
    VectorWriterData *pWriter;
    OGRGeometryH hGeometry;
    int nNewWKBSize;
    unsigned char *pCurrWKB;
    int n, bFill = 0, nHalfCrossSize = GetDefaultHalfCrossSize(self);
    NPY_BEGIN_THREADS_DEF;

    char *kwlist[] = {"ogrfeature", "boundingbox", "xsize", "ysize", 
        "linewidth", "fill", "halfCrossSize", NULL};
    if( !PyArg_ParseTupleAndKeywords(args, kwds, "OOiii|ii:rasterizeFeature", kwlist, 
            &pPythonFeature, &pBBoxObject, &nXSize, &nYSize, &nLineWidth, &bFill, 
            &nHalfCrossSize))
        return NULL;

    pPtr = getUnderlyingPtrFromSWIGPyObject(pPythonFeature, GETSTATE(self)->error);
    if( pPtr == NULL )
        return NULL;
    hOGRFeature = (OGRFeatureH)pPtr;

    if( !PySequence_Check(pBBoxObject))
    {
        PyErr_SetString(GETSTATE(self)->error, "second argument must be a sequence");
        return NULL;
    }

    if( PySequence_Size(pBBoxObject) != 4 )
    {
        PyErr_SetString(GETSTATE(self)->error, "sequence must have 4 elements");
        return NULL;
    }

    for( n = 0; n < 4; n++ )
    {
        o = PySequence_GetItem(pBBoxObject, n);
        if( !PyFloat_Check(o) )
        {
            PyErr_SetString(GETSTATE(self)->error, "Must be a sequence of floats" );
            Py_DECREF(o);
            return NULL;
        }
        adExtents[n] = PyFloat_AsDouble(o);
        Py_DECREF(o);
    }

    /* create output array - all 0 to begin with */
    dims[0] = nYSize;
    dims[1] = nXSize;
    pOutArray = PyArray_ZEROS(2, dims, NPY_UINT8, 0);
    if( pOutArray == NULL )
    {
        PyErr_SetString(GETSTATE(self)->error, "Unable to allocate array" );
        return NULL;
    }

    /* set up the object that does the writing */
    pWriter = VectorWriter_create((PyArrayObject*)pOutArray, adExtents, nLineWidth, bFill, nHalfCrossSize);
    
    hGeometry = OGR_F_GetGeometryRef(hOGRFeature);
    if( hGeometry != NULL )
    {
        /* how big a buffer do we need? */
        nNewWKBSize = OGR_G_WkbSize(hGeometry);
        pCurrWKB = (unsigned char*)malloc(nNewWKBSize);
        if( pCurrWKB == NULL )
        {
            /* malloc failed - bail out*/
            Py_DECREF(pOutArray);
            VectorWriter_destroy(pWriter);
            PyErr_SetString(GETSTATE(self)->error, "memory allocation failed");
            return NULL;
        }
        else
        {
            /* Only allow other threads to run if worthwhile */
            if( nNewWKBSize > GIL_WKB_SIZE_THRESHOLD )
            {
                NPY_BEGIN_THREADS;
            }

            /* read it in*/
            OGR_G_ExportToWkb(hGeometry, WKB_BYTE_ORDER, pCurrWKB);
            /* write it to array*/
            VectorWriter_processAll(pWriter, pCurrWKB);
            free( pCurrWKB );
        }
    }
    VectorWriter_destroy(pWriter);
    NPY_END_THREADS;

    return pOutArray;
}

static PyObject *vectorrasterizer_rasterizeGeometry(PyObject *self, PyObject *args, PyObject *kwds)
{
    PyObject *pPythonGeometry; /* of type ogr.Geometry*/
    PyObject *pBBoxObject; /* must be a sequence*/
    int nXSize, nYSize, nLineWidth;
    void *pPtr;
    double adExtents[4];
    PyObject *o;
    npy_intp dims[2];
    PyObject *pOutArray;
    VectorWriterData *pWriter;
    OGRGeometryH hGeometry;
    int nNewWKBSize;
    unsigned char *pCurrWKB;
    int n, bFill = 0, nHalfCrossSize = GetDefaultHalfCrossSize(self);
    NPY_BEGIN_THREADS_DEF;

    char *kwlist[] = {"ogrgeometry", "boundingbox", "xsize", "ysize", "linewidth", 
        "fill", "halfCrossSize", NULL};
    if( !PyArg_ParseTupleAndKeywords(args, kwds, "OOiii|ii:rasterizeGeometry", kwlist,
            &pPythonGeometry, &pBBoxObject, &nXSize, &nYSize, &nLineWidth, &bFill, 
            &nHalfCrossSize))
        return NULL;

    pPtr = getUnderlyingPtrFromSWIGPyObject(pPythonGeometry, GETSTATE(self)->error);
    if( pPtr == NULL )
        return NULL;
    hGeometry = (OGRGeometryH)pPtr;

    if( !PySequence_Check(pBBoxObject))
    {
        PyErr_SetString(GETSTATE(self)->error, "second argument must be a sequence");
        return NULL;
    }

    if( PySequence_Size(pBBoxObject) != 4 )
    {
        PyErr_SetString(GETSTATE(self)->error, "sequence must have 4 elements");
        return NULL;
    }

    for( n = 0; n < 4; n++ )
    {
        o = PySequence_GetItem(pBBoxObject, n);
        if( !PyFloat_Check(o) )
        {
            PyErr_SetString(GETSTATE(self)->error, "Must be a sequence of floats" );
            Py_DECREF(o);
            return NULL;
        }
        adExtents[n] = PyFloat_AsDouble(o);
        Py_DECREF(o);
    }

    /* create output array - all 0 to begin with */
    dims[0] = nYSize;
    dims[1] = nXSize;
    pOutArray = PyArray_ZEROS(2, dims, NPY_UINT8, 0);
    if( pOutArray == NULL )
    {
        PyErr_SetString(GETSTATE(self)->error, "Unable to allocate array" );
        return NULL;
    }

    /* set up the object that does the writing */
    pWriter = VectorWriter_create((PyArrayObject*)pOutArray, adExtents, nLineWidth, bFill, nHalfCrossSize);

    if( hGeometry != NULL )
    {
        /* how big a buffer do we need? */
        nNewWKBSize = OGR_G_WkbSize(hGeometry);
        pCurrWKB = (unsigned char*)malloc(nNewWKBSize);
        if( pCurrWKB == NULL )
        {
            /* malloc failed - bail out*/
            Py_DECREF(pOutArray);
            VectorWriter_destroy(pWriter);
            PyErr_SetString(GETSTATE(self)->error, "memory allocation failed");
            return NULL;
        }
        else
        {
            /* Only allow other threads to run if worthwhile */
            if( nNewWKBSize > GIL_WKB_SIZE_THRESHOLD )
            {
                NPY_BEGIN_THREADS;
            }

            /* read it in*/
            OGR_G_ExportToWkb(hGeometry, WKB_BYTE_ORDER, pCurrWKB);
            /* write it to array*/
            VectorWriter_processAll(pWriter, pCurrWKB);
            free( pCurrWKB );
        }
    }
    VectorWriter_destroy(pWriter);
    NPY_END_THREADS;

    return pOutArray;
}

static PyObject *vectorrasterizer_rasterizeWKB(PyObject *self, PyObject *args, PyObject *kwds)
{
    const unsigned char *pszWKB = NULL;
    Py_ssize_t nWKBSize = 0;
    PyObject *pBBoxObject; /* must be a sequence*/
    int nXSize, nYSize, nLineWidth;
    double adExtents[4];
    PyObject *o;
    npy_intp dims[2];
    PyObject *pOutArray;
    VectorWriterData *pWriter;
    int n, bFill = 0, nHalfCrossSize = GetDefaultHalfCrossSize(self);
    NPY_BEGIN_THREADS_DEF;

    char *kwlist[] = {"bytes", "boundingbox", "xsize", "ysize", "linewidth", 
        "fill", "halfCrossSize", NULL};
    if( !PyArg_ParseTupleAndKeywords(args, kwds, "y#Oiii|ii:rasterizeWKB", kwlist,
            &pszWKB, &nWKBSize, &pBBoxObject, &nXSize, &nYSize, &nLineWidth, 
            &bFill, &nHalfCrossSize))
        return NULL;

    if( !PySequence_Check(pBBoxObject))
    {
        PyErr_SetString(GETSTATE(self)->error, "second argument must be a sequence");
        return NULL;
    }

    if( PySequence_Size(pBBoxObject) != 4 )
    {
        PyErr_SetString(GETSTATE(self)->error, "sequence must have 4 elements");
        return NULL;
    }
    
    for( n = 0; n < 4; n++ )
    {
        o = PySequence_GetItem(pBBoxObject, n);
        if( !PyFloat_Check(o) )
        {
            PyErr_SetString(GETSTATE(self)->error, "Must be a sequence of floats" );
            Py_DECREF(o);
            return NULL;
        }
        adExtents[n] = PyFloat_AsDouble(o);
        Py_DECREF(o);
    }

    /* create output array - all 0 to begin with */
    dims[0] = nYSize;
    dims[1] = nXSize;
    pOutArray = PyArray_ZEROS(2, dims, NPY_UINT8, 0);
    if( pOutArray == NULL )
    {
        PyErr_SetString(GETSTATE(self)->error, "Unable to allocate array" );
        return NULL;
    }
    
    /* Only allow other threads to run if worthwhile */
    if( nWKBSize > GIL_WKB_SIZE_THRESHOLD )
    {
        NPY_BEGIN_THREADS;
    }
    
    /* set up the object that does the writing */
    if( pszWKB != NULL )
    {
        pWriter = VectorWriter_create((PyArrayObject*)pOutArray, adExtents, nLineWidth, bFill, nHalfCrossSize);
    
        VectorWriter_processWKB(pWriter, pszWKB);

        VectorWriter_destroy(pWriter);
    }
    
    NPY_END_THREADS;

    return pOutArray;
}

/* Our list of functions in this module*/
static PyMethodDef VectorRasterizerMethods[] = {
    {"rasterizeLayer", (PyCFunction)vectorrasterizer_rasterizeLayer, METH_VARARGS | METH_KEYWORDS, 
"read an OGR dataset and vectorize outlines to numpy array:\n"
"call signature: arr = rasterizeLayer(ogrlayer, boundingbox, xsize, ysize, linewidth, sql, fill=False, halfCrossSize=HALF_CROSS_SIZE)\n"
"where:\n"
"  ogrlayer is an instance of ogr.Layer\n"
"  boundingbox is a sequence that contains (tlx, tly, brx, bry)\n"
"  xsize,ysize size of output array\n"
"  linewidth is the width of the line\n"
"  sql is the attribute filter. Pass None or SQL string\n"
"  fill is an optional argument that determines if polygons are filled in\n"
"  halfCrossSize is an optional argument that controls the size of the crosses drawn for points. Defaults to the value of HALF_CROSS_SIZE."},
    {"rasterizeFeature", (PyCFunction)vectorrasterizer_rasterizeFeature, METH_VARARGS | METH_KEYWORDS, 
"read an OGR feature and vectorize outlines to numpy array:\n"
"call signature: arr = rasterizeFeature(ogrfeature, boundingbox, xsize, ysize, linewidth, fill=False, halfCrossSize=HALF_CROSS_SIZE)\n"
"where:\n"
"  ogrfeature is an instance of ogr.Feature\n"
"  boundingbox is a sequence that contains (tlx, tly, brx, bry)\n"
"  xsize,ysize size of output array\n"
"  linewidth is the width of the line\n"
"  fill is an optional argument that determines if polygons are filled in\n"
"  halfCrossSize is an optional argument that controls the size of the crosses drawn for points. Defaults to the value of HALF_CROSS_SIZE."},
    {"rasterizeGeometry", (PyCFunction)vectorrasterizer_rasterizeGeometry, METH_VARARGS | METH_KEYWORDS,
"read an OGR Geometry and vectorize outlines to numpy array:\n"
"call signature: arr = rasterizeGeometry(ogrgeometry, boundingbox, xsize, ysize, linewidth, fill=False, halfCrossSize=HALF_CROSS_SIZE)\n"
"where:\n"
"  ogrgeometry is an instance of ogr.Geometry\n"
"  boundingbox is a sequence that contains (tlx, tly, brx, bry)\n"
"  xsize,ysize size of output array\n"
"  linewidth is the width of the line\n"
"  fill is an optional argument that determines if polygons are filled in\n"
"  halfCrossSize is an optional argument that controls the size of the crosses drawn for points. Defaults to the value of HALF_CROSS_SIZE."},
    {"rasterizeWKB", (PyCFunction)vectorrasterizer_rasterizeWKB, METH_VARARGS | METH_KEYWORDS,
"read an WKB from a bytes object and vectorize outlines to numpy array:\n"
"call signature: arr = rasterizeWKB(bytes, boundingbox, xsize, ysize, linewidth, fill=False, halfCrossSize=HALF_CROSS_SIZE)\n"
"where:\n"
"  bytes is a bytes object (assumed to be correct endian).\n"
"  boundingbox is a sequence that contains (tlx, tly, brx, bry)\n"
"  xsize,ysize size of output array\n"
"  linewidth is the width of the line\n"
"  fill is an optional argument that determines if polygons are filled in\n"
"  halfCrossSize is an optional argument that controls the size of the crosses drawn for points. Defaults to the value of HALF_CROSS_SIZE."},
    {NULL}        /* Sentinel */
};

static int vectorrasterizer_traverse(PyObject *m, visitproc visit, void *arg) 
{
    Py_VISIT(GETSTATE(m)->error);
    return 0;
}

static int vectorrasterizer_clear(PyObject *m) 
{
    Py_CLEAR(GETSTATE(m)->error);
    return 0;
}

static struct PyModuleDef moduledef = {
        PyModuleDef_HEAD_INIT,
        "vectorrasterizer",
        NULL,
        sizeof(struct VectorRasterizerState),
        VectorRasterizerMethods,
        NULL,
        vectorrasterizer_traverse,
        vectorrasterizer_clear,
        NULL
};

PyMODINIT_FUNC 
PyInit_vectorrasterizer(void)
{
    PyObject *pModule;
    struct VectorRasterizerState *state;

    /* initialize the numpy stuff */
    import_array();

    pModule = PyModule_Create(&moduledef);
    if( pModule == NULL )
        return NULL;

    state = GETSTATE(pModule);

    /* Create and add our exception type */
    state->error = PyErr_NewException("vectorrasterizer.error", NULL, NULL);
    if( state->error == NULL )
    {
        Py_DECREF(pModule);
        return NULL;
    }
    if( PyModule_AddObject(pModule, "error", state->error) != 0)
    {
        Py_DECREF(pModule);
        return NULL;
    }
    
    /* Constant for HALF_CROSS_SIZE */
    if( PyModule_AddIntMacro(pModule, HALF_CROSS_SIZE) != 0 )
    {
        Py_DECREF(pModule);
        return NULL;
    }

    return pModule;
}
