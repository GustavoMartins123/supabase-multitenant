import 'package:flutter/material.dart';

class UserAvatarThumbnail extends StatelessWidget {
  const UserAvatarThumbnail({
    super.key,
    required this.pictureUrl,
    required this.size,
    required this.borderRadius,
    required this.backgroundColor,
    required this.fallback,
  });

  final String? pictureUrl;
  final double size;
  final BorderRadius borderRadius;
  final Color backgroundColor;
  final Widget fallback;

  @override
  Widget build(BuildContext context) {
    final rawUrl = pictureUrl?.trim() ?? '';
    final fallbackWidget = Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: borderRadius,
      ),
      alignment: Alignment.center,
      child: fallback,
    );

    if (rawUrl.isEmpty) return fallbackWidget;

    final resolvedUrl = Uri.base.resolve(rawUrl).toString();
    return ClipRRect(
      borderRadius: borderRadius,
      child: Image.network(
        resolvedUrl,
        width: size,
        height: size,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => fallbackWidget,
      ),
    );
  }
}
