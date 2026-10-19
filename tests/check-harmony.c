/* Run against the built library, not the system FreeType. See README.md. */
#include <ft2build.h>
#include FT_FREETYPE_H
#include FT_LCD_FILTER_H
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define CHECK(call) do { \
  FT_Error err = (call); \
  if (err) { fprintf(stderr, "%s failed: %d\n", #call, err); exit(1); } \
} while (0)

static uint64_t bitmap_hash(FT_Face face, FT_ULong character, int flags)
{
  CHECK(FT_Load_Char(face, character, flags | FT_LOAD_RENDER | FT_LOAD_NO_BITMAP));
  FT_GlyphSlot slot = face->glyph;
  FT_Bitmap *b = &slot->bitmap;
  uint64_t hash = UINT64_C(14695981039346656037);
  unsigned long meta[] = {b->rows, b->width, b->pixel_mode,
                         slot->bitmap_left, slot->bitmap_top};
  for (unsigned i = 0; i < sizeof(meta) / sizeof(meta[0]); ++i)
    hash = (hash ^ meta[i]) * UINT64_C(1099511628211);
  for (unsigned y = 0; y < b->rows; ++y)
    for (unsigned x = 0; x < b->width; ++x)
      hash = (hash ^ b->buffer[(long)y * b->pitch + x]) * UINT64_C(1099511628211);
  return hash;
}

int main(int argc, char **argv)
{
  if (argc != 2) {
    fprintf(stderr, "Usage: %s /path/to/scalable-font.ttf\n", argv[0]);
    return 2;
  }
  FT_Library libraries[3];
  FT_Face faces[3];
  FT_Vector qdoled[3] = {{-17, -18}, {0, 16}, {17, -17}};
  FT_Vector striped[3] = {{-21, 0}, {0, 0}, {21, 0}};
  for (unsigned i = 0; i < 3; ++i) {
    CHECK(FT_Init_FreeType(&libraries[i]));
    CHECK(FT_New_Face(libraries[i], argv[1], 0, &faces[i]));
  }
  CHECK(FT_Library_SetLcdGeometry(libraries[1], qdoled));
  CHECK(FT_Library_SetLcdGeometry(libraries[2], striped));
  unsigned differences = 0, cases = 0;
  const unsigned sizes[] = {9, 12, 16, 24};
  const char *characters = "AWmi|,g@";
  for (unsigned s = 0; s < sizeof(sizes) / sizeof(sizes[0]); ++s) {
    for (unsigned i = 0; i < 3; ++i)
      CHECK(FT_Set_Pixel_Sizes(faces[i], 0, sizes[s]));
    for (const char *c = characters; *c; ++c) {
      for (unsigned i = 0; i < 3; ++i) {
        if (!FT_Get_Char_Index(faces[i], (unsigned char)*c)) {
          fprintf(stderr, "Font is missing a test character\n");
          return 1;
        }
      }
      uint64_t actual = bitmap_hash(faces[0], *c, FT_LOAD_TARGET_LCD);
      uint64_t expected = bitmap_hash(faces[1], *c, FT_LOAD_TARGET_LCD);
      if (actual != expected || faces[0]->glyph->bitmap.pixel_mode != FT_PIXEL_MODE_LCD) {
        fprintf(stderr, "Default LCD geometry does not match QD-OLED geometry\n");
        return 1;
      }
      differences += actual != bitmap_hash(faces[2], *c, FT_LOAD_TARGET_LCD);
      if (bitmap_hash(faces[0], *c, FT_LOAD_TARGET_NORMAL) !=
          bitmap_hash(faces[2], *c, FT_LOAD_TARGET_NORMAL)) {
        fprintf(stderr, "LCD geometry changed grayscale rendering\n");
        return 1;
      }
      ++cases;
    }
  }
  for (unsigned i = 0; i < 3; ++i) {
    CHECK(FT_Done_Face(faces[i]));
    CHECK(FT_Done_FreeType(libraries[i]));
  }
  if (!differences) {
    fprintf(stderr, "QD-OLED and striped LCD rendering unexpectedly identical\n");
    return 1;
  }
  printf("PASS: %u glyph/size cases match QD-OLED defaults; %u differ from RGB stripes; grayscale unchanged\n",
         cases, differences);
  return 0;
}
