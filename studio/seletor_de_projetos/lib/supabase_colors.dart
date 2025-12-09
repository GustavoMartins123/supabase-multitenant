// supabase_colors.dart
// Supabase Studio Color Palette - Use across all project files
import 'package:flutter/material.dart';

class SupabaseColors {
  // BACKGROUNDS
  static const Color bg100 = Color(0xFF171717);  // Darkest - main scaffold
  static const Color bg200 = Color(0xFF1C1C1C);  // Dialog backgrounds
  static const Color bg300 = Color(0xFF232323);  // Input backgrounds
  static const Color bg400 = Color(0xFF2A2A2A);  // Hover states
  
  // SURFACES (Cards, containers)
  
  static const Color surface100 = Color(0xFF1F1F1F);  // Card default
  static const Color surface200 = Color(0xFF262626);  // Card hover
  static const Color surface300 = Color(0xFF2E2E2E);  // Elevated surfaces

  // BRAND (Supabase Green)
  
  static const Color brand = Color(0xFF3ECF8E);       // Primary brand
  static const Color brandDark = Color(0xFF2DA86D);   // Pressed state
  static const Color brandLight = Color(0xFF4AE19B);  // Hover state

  // STATUS COLORS
  
  static const Color success = Color(0xFF3ECF8E);  // Green (same as brand)
  static const Color warning = Color(0xFFF5A623);  // Orange/Amber
  static const Color error = Color(0xFFEF4444);    // Red
  static const Color info = Color(0xFF3B82F6);     // Blue
  
  // TEXT COLORS
  
  static const Color textPrimary = Color(0xFFEDEDED);    // Main text
  static const Color textSecondary = Color(0xFFA1A1A1);  // Secondary text
  static const Color textMuted = Color(0xFF6B6B6B);      // Muted/disabled
  
  // BORDER COLORS
  
  static const Color border = Color(0xFF2E2E2E);         // Default border
  static const Color borderHover = Color(0xFF3E3E3E);    // Hover border
  static const Color borderFocus = Color(0xFF3ECF8E);    // Focus (brand)

  // SPECIAL
  
  static const Color favorite = Color(0xFFFBBF24);  // Yellow star
  
  // HELPER METHODS

  /// Get theme data with Supabase colors
  static ThemeData get darkTheme => ThemeData(
    colorSchemeSeed: brand,
    brightness: Brightness.dark,
    useMaterial3: true,
    scaffoldBackgroundColor: bg100,
    cardColor: surface100,
    dividerColor: border,
    dialogBackgroundColor: bg200,
    appBarTheme: const AppBarTheme(
      backgroundColor: bg100,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: surface300,
      contentTextStyle: const TextStyle(color: textPrimary),
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: bg300,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: const BorderSide(color: border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: const BorderSide(color: border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: const BorderSide(color: borderFocus, width: 2),
      ),
      labelStyle: const TextStyle(color: textSecondary),
      hintStyle: const TextStyle(color: textMuted),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: brand,
        foregroundColor: bg100,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: textSecondary,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
      ),
    ),
    popupMenuTheme: PopupMenuThemeData(
      color: surface300,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: const BorderSide(color: border),
      ),
    ),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(
        color: surface300,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: border),
      ),
      textStyle: const TextStyle(color: textPrimary, fontSize: 12),
    ),
  );
}